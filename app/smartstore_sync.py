import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models import MarketAccount, MarketProductRaw, MarketListing, Product
from app.smartstore_client import SmartStoreClient

logger = logging.getLogger(__name__)

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

    # 1. 네이버 상품 등록 페이로드 구성
    # 실제 구현 시 카테고리 ID, 배송비 템플릿 등 필수 정보가 필요함
    payload = {
        "originProduct": {
            "statusType": "SALE",
            "name": product.processed_name or product.name,
            "salePrice": int(product.selling_price or 0),
            "stockQuantity": 999,
            "detailContent": product.description or "",
            "images": {
                "representativeImage": {"url": product.processed_image_urls[0]} if product.processed_image_urls else None
            },
            # 필수 하드코딩 필드 (예시)
            "deliveryInfo": {
                "deliveryType": "DELIVERY",
                "deliveryAttributeType": "NORMAL",
                "deliveryCompany": "CJGLS",
                "deliveryBundleGroupPriority": 1
            },
            "category": {
                "categoryId": "50000000" # TODO: 카테고리 매핑 로직 필요
            }
        }
    }

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
        product.processing_status = "COMPLETED"
        session.commit()
        return {"status": "success", "market_item_id": origin_product_no}
    else:
        logger.error(f"SmartStore registration failed: {result}")
        return {"status": "error", "message": result.get("message", "Unknown error")}
