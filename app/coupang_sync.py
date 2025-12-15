from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.coupang_client import CoupangClient
from app.models import MarketAccount, MarketProductRaw, SupplierRawFetchLog, Product, MarketListing

logger = logging.getLogger(__name__)


def _get_client_for_account(account: MarketAccount) -> CoupangClient:
    creds = account.credentials
    if not creds:
        raise ValueError(f"Account {account.name} has no credentials")
    
    return CoupangClient(
        access_key=creds.get("access_key", ""),
        secret_key=creds.get("secret_key", ""),
        vendor_id=creds.get("vendor_id", "")
    )


def sync_coupang_products(session: Session, account_id: uuid.UUID) -> int:
    """
    Syncs products for a specific Coupang account.
    Returns the number of products processed.
    """
    account = session.get(MarketAccount, account_id)
    if not account:
        logger.error(f"MarketAccount {account_id} not found")
        return 0
        
    if account.market_code != "COUPANG":
        logger.error(f"Account {account.name} is not a Coupang account")
        return 0
        
    if not account.is_active:
        logger.info(f"Account {account.name} is inactive, skipping sync")
        return 0

    try:
        client = _get_client_for_account(account)
    except Exception as e:
        logger.error(f"Failed to initialize client for {account.name}: {e}")
        return 0

    logger.info(f"Starting product sync for {account.name} ({account.market_code})")
    
    total_processed = 0
    next_token = None
    
    while True:
        # Fetch page
        code, data = client.get_products(
            next_token=next_token,
            max_per_page=50  # Max allowed by Coupang
        )
        
        # Log fetch attempt (optional but good for debugging)
        _log_fetch(session, account, "get_products", {"nextToken": next_token}, code, data)
        
        if code != 200:
            logger.error(f"Failed to fetch products for {account.name}: {data}")
            break
            
        products = data.get("data", [])
        if not products:
            break
            
        # Upsert Raw Data
        for p in products:
            seller_product_id = str(p.get("sellerProductId"))
            stmt = insert(MarketProductRaw).values(
                market_code="COUPANG",
                account_id=account.id,
                market_item_id=seller_product_id,
                raw=p
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["market_code", "account_id", "market_item_id"],
                set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at}
            )
            session.execute(stmt)
            
        session.commit()
        total_processed += len(products)
        
        next_token = data.get("nextToken")
        if not next_token:
            break
            
    logger.info(f"Finished product sync for {account.name}. Total: {total_processed}")
    return total_processed


def _log_fetch(
    session: Session, 
    account: MarketAccount, 
    endpoint: str, 
    request_payload: Any, 
    status: int, 
    response_payload: Any
) -> None:
    # 기존 SupplierRawFetchLog를 재사용하거나 MarketRawFetchLog를 새로 생성해야 할까요?
    # 스키마 계획에서는 SupplierRawFetchLog만 언급되었습니다.
    # 당장은 DB 로깅을 건너뛰거나 'COUPANG' 코드로 Supplier 테이블을 재사용하는 것이 좋겠습니다.
    # SupplierRawFetchLog에는 'account_id'가 있지만 SupplierAccount를 의미할 수 있습니다.
    # 스키마를 고려할 때, MarketRawFetchLog를 추가하기 전까지는 stdout/logger에만 로깅하는 편이 낫습니다.
    pass


def register_product(session: Session, account_id: uuid.UUID, product_id: uuid.UUID) -> bool:
    """
    쿠팡에 상품을 등록합니다.
    성공 시 True, 실패 시 False를 반환합니다.
    """
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code != "COUPANG":
        logger.error(f"쿠팡 등록을 위한 계정이 유효하지 않습니다: {account_id}")
        return False
        
    product = session.get(Product, product_id)
    if not product:
        logger.error(f"상품을 찾을 수 없습니다: {product_id}")
        return False

    try:
        client = _get_client_for_account(account)
    except Exception as e:
        logger.error(f"클라이언트 초기화 실패: {e}")
        return False

    # 1. 데이터 준비
    # 설정에 제공되지 않은 경우 센터 코드를 자동 감지합니다 (현재는 첫 번째 사용 가능한 센터 조회)
    return_center_code, outbound_center_code = _get_default_centers(client)
    if not return_center_code or not outbound_center_code:
        logger.error("반품/출고지 센터 코드를 확인할 수 없습니다.")
        return False

    # 기본 매핑
    # 1.5 카테고리 예측
    predicted_category_code = 77800 # 기본값 (기타/미분류 등)
    try:
        # 가공된 이름 명 또는 원본 이름 사용
        pred_name = product.processed_name or product.name
        code, pred_data = client.predict_category(pred_name)
        if code == 200 and pred_data.get("code") == "SUCCESS":
             # 응답 구조: data -> predictedCategoryCode (문서/경험 기반 추정)
             # 실제 응답이 {"data": {"predictedCategoryCode": "12345", ...}} 형태라고 가정
             # 혹은 {"data": "12345"} 일 수도 있음. 가장 안전한 파싱 필요.
             # 보통 쿠팡 응답은 `data` 필드에 결과를 담음.
             resp_data = pred_data.get("data")
             if isinstance(resp_data, dict) and "predictedCategoryCode" in resp_data:
                 predicted_category_code = int(resp_data["predictedCategoryCode"])
                 logger.info(f"카테고리 예측 성공: {pred_name} -> {predicted_category_code}")
             elif isinstance(resp_data, (str, int)):
                 # 만약 data 자체가 코드라면
                 predicted_category_code = int(resp_data)
                 logger.info(f"카테고리 예측 성공 (Direct): {pred_name} -> {predicted_category_code}")
        else:
            logger.warning(f"카테고리 예측 실패: Code {code}, Msg {pred_data}")
    except Exception as e:
        logger.warning(f"카테고리 예측 중 오류 발생: {e}")

    payload = _map_product_to_coupang_payload(product, account, return_center_code, outbound_center_code, predicted_category_code)
    
    # 2. API 호출
    code, data = client.create_product(payload)
    _log_fetch(session, account, "create_product", payload, code, data)

    # 성공 조건: HTTP 200 이면서 body의 code가 SUCCESS
    if code != 200 or data.get("code") != "SUCCESS":
        logger.error(f"상품 생성 실패 (ID: {product.id}). HTTP: {code}, Msg: {data}")
        # 처리 상태 업데이트
        product.processing_status = "FAILED"
        session.commit()
        return False

    # 3. 성공 처리
    # data['data']에 sellerProductId (등록상품ID)가 포함됨
    seller_product_id = str(data.get("data"))
    
    # MarketListing 생성 또는 업데이트
    stmt = insert(MarketListing).values(
        product_id=product.id,
        market_account_id=account.id,
        market_item_id=seller_product_id,
        status="ACTIVE" # 'requested' 플래그에 따라 IN_REVIEW 상태일 수도 있음
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["market_account_id", "market_item_id"],
        set_={"status": "ACTIVE", "linked_at": func.now()}
    )
    session.execute(stmt)
    
    product.processing_status = "COMPLETED"
    session.commit()
    
    logger.info(f"상품 등록 성공 (ID: {product.id}, sellerProductId: {seller_product_id})")
    return True


def _get_default_centers(client: CoupangClient) -> tuple[str | None, str | None]:
    """
    첫 번째로 사용 가능한 반품지 및 출고지 센터 코드를 조회합니다.
    Returns (return_center_code, outbound_center_code)
    """
    # 출고지 (Outbound)
    rc, data = client.get_outbound_shipping_centers(page_size=1)
    outbound_code = None
    if rc == 200 and data.get("data") and data["data"].get("content"):
        outbound_code = str(data["data"]["content"][0]["outboundShippingPlaceCode"])
        
    # 반품지 (Return)
    rc, data = client.get_return_shipping_centers(page_size=1)
    return_code = None
    if rc == 200 and data.get("data") and data["data"].get("content"):
        return_code = str(data["data"]["content"][0]["returnCenterCode"])
        
    return return_code, outbound_code


def _map_product_to_coupang_payload(
    product: Product, 
    account: MarketAccount, 
    return_center_code: str, 
    outbound_center_code: str,
    predicted_category_code: int = 77800
) -> dict[str, Any]:
    """
    내부 Product 모델을 쿠팡 API Payload로 매핑합니다.
    """
    
    # 가공된 이름이 있으면 사용, 없으면 원본 이름 사용
    name_to_use = product.processed_name if product.processed_name else product.name
    
    # 상세설명 (Contents)
    # 원본 텍스트라면 간단한 HTML 태그로 감쌈. 보통 공급사 데이터가 이미 HTML임.
    description_html = product.description or "<p>상세설명 없음</p>"
    
    # 이미지
    # 가공된 이미지 우선 사용
    images = []
    if product.processed_image_urls:
         # processed_image_urls는 JSONB 리스트
         img_list = product.processed_image_urls
         if isinstance(img_list, list):
             for url in img_list:
                 images.append({"imageOrder": len(images), "imageType": "REPRESENTATION", "vendorPath": url})
    
    # 가공된 이미지가 없을 경우 처리 방안 필요
    # 현재는 선행 단계에서 처리되었다고 가정함.
    if not images:
        pass

    # 아이템 (옵션)
    # 현재는 단일 옵션 매핑 (Drop 01 범위)
    # 변형 상품(옵션)이 있다면 반복문 필요
    item_payload = {
        "itemName": name_to_use[:150], # 최대 150자
        "originalPrice": product.selling_price, # 할인가 적용 시 정가를 높게 설정 가능
        "salePrice": product.selling_price,
        "maximumBuyCount": 100, # 기본값
        "images": images,
        "attributes": [], # TODO: 카테고리 속성 매핑 필요 (예측된 카테고리에 따라 필수 속성이 다름)
        "contents": [
            {
                "contentsType": "HTML",
                "contentDetails": [{"content": description_html, "detailType": "TEXT"}] 
            }
        ],
        "noticeCategories": [
             {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "제품소재", "content": "상세페이지 참조"},
             {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "색상", "content": "상세페이지 참조"},
             {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "치수", "content": "상세페이지 참조"},
             {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "제조자(수입자)", "content": "상세페이지 참조"},
             {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "제조국", "content": "상세페이지 참조"},
             {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "취급시 주의사항", "content": "상세페이지 참조"},
             {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "품질보증기준", "content": "상세페이지 참조"},
             {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "A/S 책임자와 전화번호", "content": "상세페이지 참조"},
        ] # 위탁판매 특성상 안전하게 '기타 재화'로 기본 설정
    }

    payload = {
        "displayCategoryCode": predicted_category_code, 
        # 예측된 카테고리 코드를 사용.
        # 주의: 일부 카테고리는 필수 속성(attributes)이 없으면 등록 실패할 수 있음.
        # 향후 predict_category 응답에 포함된 attributes 메타데이터를 활용하여 자동 매핑 고도화 필요.
        "sellerProductName": name_to_use[:100],
        "vendorId": account.credentials.get("vendor_id"),
        "displayProductName": name_to_use[:100],
        "brand": product.brand or "Detailed Page",
        "generalProductName": name_to_use, # 보통 노출명과 동일
        "productOrigin": "수입산", # 위탁판매 기본
        "deliveryMethod": "SEQUENCIAL", # 일반 배송
        "deliveryCompanyCode": "KDEXP", # 기본 택배사 (경동? 설정값 확인 필요)
        "deliveryChargeType": "FREE", # 일단 무료배송으로 시작
        "returnCenterCode": return_center_code,
        "returnCharge": 5000, # 기본 반품비
        "outboundShippingPlaceCode": outbound_center_code,
        "vendorUserId": account.credentials.get("vendor_user_id", "user"), # Wing ID
        "requested": True, # 자동 승인 요청
        "items": [item_payload]
    }
    
    return payload
