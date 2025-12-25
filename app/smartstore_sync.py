import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models import MarketAccount, MarketProductRaw, MarketListing, Product, SupplierItemRaw
from app.smartstore_client import SmartStoreClient
from app.services.coupang_ready_service import collect_image_urls_from_raw

logger = logging.getLogger(__name__)

def _get_original_image_urls(session: Session, product: Product) -> list[str]:
    if product.supplier_item_id:
        raw_item = session.get(SupplierItemRaw, product.supplier_item_id)
        raw = raw_item.raw if raw_item and isinstance(raw_item.raw, dict) else {}
        return collect_image_urls_from_raw(raw)
    return []

def _get_client_for_smartstore(account: MarketAccount) -> SmartStoreClient:
    creds = account.credentials
    if not creds:
        raise ValueError(f"Account {account.name} has no credentials")
    
    client_id = creds.get("client_id")
    client_secret = creds.get("client_secret")
    if not client_id or not client_secret:
        raise ValueError(f"Account {account.name} is missing Client ID or Secret")

    return SmartStoreClient(client_id=client_id, client_secret=client_secret)

def sync_smartstore_products(session: Session, account_id: uuid.UUID) -> int:
    """
    네이버 스마트스토어 계정의 상품 목록을 동기화합니다.
    """
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code != "SMARTSTORE":
        logger.error(f"Invalid account for SmartStore sync: {account_id}")
        return 0

    client = _get_client_for_smartstore(account)
    total_processed = 0
    page = 1
    size = 50

    while True:
        code, data = client.get_products(page=page, size=size)
        if code != 200:
            logger.error(f"Failed to fetch SmartStore products: {data}")
            break

        # 네이버 커머스 API 응답 구조에 맞게 조정 (예시: data.content)
        products = data.get("content", []) if isinstance(data, dict) else []
        if not products:
            break

        for p in products:
            origin_product_no = str(p.get("originProductNo"))
            
            # MarketProductRaw 저장
            stmt = insert(MarketProductRaw).values(
                market_code="SMARTSTORE",
                account_id=account.id,
                market_item_id=origin_product_no,
                raw=p,
                fetched_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["market_code", "account_id", "market_item_id"],
                set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at},
            )
            session.execute(stmt)

            # MarketListing 상태 동기화 (간단히)
            listing = session.execute(
                select(MarketListing)
                .where(MarketListing.market_account_id == account.id)
                .where(MarketListing.market_item_id == origin_product_no)
            ).scalars().first()
            
            if not listing:
                # 새로운 상장 정보 생성 (필요 시)
                pass

        session.commit()
        total_processed += len(products)
        
        # 페이징 루프 종료 조건
        if len(products) < size:
            break
        page += 1

    logger.info(f"SmartStore sync completed for {account.name}. Total: {total_processed}")
    return total_processed

def delete_market_listing(session: Session, account_id: uuid.UUID, market_item_id: str) -> tuple[bool, str | None]:
    """
    네이버 스마트스토어에서 상품을 삭제(또는 판매중지)하고 DB 상태를 업데이트합니다.
    """
    account = session.get(MarketAccount, account_id)
    if not account:
        return False, "계정을 찾을 수 없습니다"

    listing = (
        session.query(MarketListing)
        .filter(MarketListing.market_account_id == account_id)
        .filter(MarketListing.market_item_id == market_item_id)
        .first()
    )

    try:
        client = _get_client_for_smartstore(account)
        code, data = client.delete_product(market_item_id)
        
        if code == 200 or code == 204:
            if listing:
                listing.status = "DELETED"
                session.commit()
            return True, None
        else:
            logger.warning(f"Deletion failed for SmartStore {market_item_id}: {data}")
            return False, data.get("message", "Unknown error")
    except Exception as e:
        logger.error(f"Error deleting SmartStore product {market_item_id}: {e}")
        return False, str(e)

def register_smartstore_product(session: Session, account_id: uuid.UUID, product_id: uuid.UUID) -> Dict[str, Any]:
    """
    가공된 상품을 네이버 스마트스토어에 등록합니다.
    """
    account = session.get(MarketAccount, account_id)
    product = session.get(Product, product_id)
    
    if not account or not product:
        return {"status": "error", "message": "Account or Product not found"}

    client = _get_client_for_smartstore(account)

    # 0. 이미지 업로드 전처리 (네이버 서버로 업로드 필수)
    # 이미지 풀백 로직: 가공된 이미지가 없으면 원본 이미지 사용
    representative_image_url = None
    processed_images = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
    
    # 후보군 구성: 가공 이미지 -> 원본 이미지 순 (검증된 도메인 위주)
    image_candidates = processed_images.copy()
    original_images = _get_original_image_urls(session, product)
    image_candidates.extend(original_images)
    
    # 중복 제거 (순서 유지)
    seen = set()
    unique_candidates = []
    for img in image_candidates:
        if not img or not (img.startswith("http://") or img.startswith("https://")):
            continue
        if img not in seen:
            unique_candidates.append(img)
            seen.add(img)
            
    # 네이버는 이미지가 없으면 다른 모든 필드에 대해 엄격한 에러(KC인증 등)를 뱉으므로 더미 필수
    # 로컬 더미 이미지 추가 (마지막 보루)
    unique_candidates.append("app/static/images/dummy.jpg")

    # 후보군 순회하며 업로드 시도
    for img_url in unique_candidates:
        uploaded_urls = client.upload_images([img_url])
        if uploaded_urls:
            representative_image_url = uploaded_urls[0]
            break
        # 너무 많이 시도하진 않게 (최대 10개)
        if unique_candidates.index(img_url) > 10:
            break
            
    if not representative_image_url:
        logger.error(f"Failed to upload any images even dummy to Naver for product {product.id}")

    creds = account.credentials or {}
    shipping_address_id = creds.get("shipping_address_id")
    return_address_id = creds.get("return_address_id")
    delivery_bundle_group_id = creds.get("delivery_bundle_group_id")
    channel_no = creds.get("channel_no")

    # 1. 카테고리 매핑 (원본 공급처 메타데이터 활용)
    leaf_category_id = "50000803" # 기본값 (펌프스)
    if product.supplier_item_id:
        raw_item = session.get(SupplierItemRaw, product.supplier_item_id)
        if raw_item and isinstance(raw_item.raw, dict):
            # 오너클랜 등에서 제공하는 네이버 카테고리 번호 추출
            metadata = raw_item.raw.get("metadata", {})
            cat_code = metadata.get("smartstoreCategoryCode")
            if cat_code:
                leaf_category_id = str(cat_code)
            else:
                # category 필드에서도 확인
                cat_obj = raw_item.raw.get("category", {})
                if isinstance(cat_obj, dict) and cat_obj.get("key"):
                    leaf_category_id = str(cat_obj.get("key"))

    # 2. 네이버 상품 등록 페이로드 구성 (v2)
    sale_price = int(product.selling_price or 0)
    # 네이버는 판매가가 10원 단위여야 함
    sale_price = (sale_price // 10) * 10

    payload = {
        "originProduct": {
            "statusType": "SALE",
            "name": product.processed_name or product.name,
            "salePrice": sale_price,
            "stockQuantity": 999,
            "detailContent": (product.description or "").replace('src="//', 'src="https://').replace('src="http://', 'src="https://'),
            "images": {
                "representativeImage": {"url": representative_image_url} if representative_image_url else None
            },
            "deliveryInfo": {
                "deliveryType": "DELIVERY",
                "deliveryAttributeType": "NORMAL",
                "deliveryCompany": "CJGLS",
                "deliveryBundleGroupPriority": 1,
                "deliveryBundleGroupId": delivery_bundle_group_id,
                "deliveryFee": {
                    "deliveryFeeType": "FREE"
                },
                "claimDeliveryInfo": {
                    "returnDeliveryFee": 3000,
                    "exchangeDeliveryFee": 6000,
                    "shippingAddressId": shipping_address_id,
                    "returnAddressId": return_address_id
                }
            },
            "leafCategoryId": leaf_category_id, 
            "detailAttribute": {
                "itemConditionType": "NEW",
                "minorPurchasable": False,
                "originAreaInfo": {
                    "originAreaCode": "0200037", 
                    "importer": "상세페이지 참조"
                },
                "afterServiceInfo": {
                    "afterServiceTelephoneNumber": creds.get("phone_number", "010-9119-0067"),
                    "afterServiceGuideContent": "상세페이지를 참고해 주세요."
                },
                "productInfoProvidedNotice": {
                    "productInfoProvidedNoticeType": "ETC",
                    "etc": {
                        "itemName": "상품 상세 참조",
                        "modelName": "상품 상세 참조",
                        "manufacturer": "상품 상세 참조",
                        "origin": "상품 상세 참조",
                        "asTelephoneNumber": "상세페이지 참조",
                        "afterServiceDirector": "판매자 상세정보 참조"
                    }
                },
                "certificationTargetConfirmType": "NOT_SUBJECT",
                "productCertificationInfos": None
            }
        },
        "smartstoreChannelProduct": {
            "naverShoppingRegistration": True,
            "channelProductDisplayStatusType": "ON"
        }
    }
    
    if channel_no:
        payload["smartstoreChannelProduct"]["channelNo"] = channel_no

    # 상세 설명 비어있으면 안됨
    if not payload["originProduct"]["detailContent"]:
        payload["originProduct"]["detailContent"] = "상품 상세 설명입니다."

    code, result = client.create_product(payload)
    
    if code == 200 or code == 201:
        origin_product_no = str(result.get("originProductNo"))
        # MarketListing 생성
        listing = MarketListing(
            product_id=product.id,
            market_account_id=account.id,
            market_item_id=origin_product_no,
            status="ACTIVE",
            store_url=f"https://smartstore.naver.com/main/products/{origin_product_no}"
        )
        session.add(listing)
        product.processing_status = "LISTED"
        session.commit()
        return {"status": "success", "market_item_id": origin_product_no}
    else:
        # 실패 시 상세 로그 기록
        logger.error(f"SmartStore registration failed for product {product.id}. Status: {code}, Response: {result}")
        # 오류 메시지에 상세 내용 포함 (네이버는 보통 invalidInputs 리스트를 줌)
        detail_msg = result.get("message", "Unknown error")
        invalid_inputs = result.get("invalidInputs")
        if invalid_inputs:
            # message 필드에 invalidInputs 상세 내용을 포함시켜 오케스트레이터 이벤트 로그에 남김
            try:
                import json
                invalid_str = json.dumps(invalid_inputs, ensure_ascii=False)
                detail_msg = f"{detail_msg} (Invalid: {invalid_str})"
            except Exception:
                detail_msg = f"{detail_msg} (Invalid: {invalid_inputs})"
            
        return {"status": "error", "message": detail_msg}
