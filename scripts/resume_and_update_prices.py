import logging
import uuid
from sqlalchemy import select, update
from app.db import get_session
from app.models import Product, MarketListing, MarketAccount
from app.coupang_client import CoupangClient
from app.session_factory import session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def resume_and_update_prices():
    with session_factory() as session:
        # 1. 대상 상품 식별 (최근 긴급 조치된 상품들 - status='DELETED' 또는 selling_price 정상화된 상품)
        # 여기서는 selling_price > 0 이고 MarketListing이 있는 상품들 중 처리가 필요한 것들
        stmt = (
            select(Product.id, Product.name, Product.selling_price, MarketListing.market_item_id, MarketListing.market_account_id)
            .join(MarketListing, Product.id == MarketListing.product_id)
            .where(Product.selling_price > 0)
            .where(MarketListing.coupang_status == "DELETED") # 앞선 스크립트에서 설정한 값
        )
        targets = session.execute(stmt).all()
        
        if not targets:
            logger.info("No targets found for price sync and resume.")
            return

        logger.info(f"Found {len(targets)} targets for price sync and resume.")

        # Account ID별로 Client 캐싱
        clients = {}

        for p_id, p_name, selling_price, seller_product_id, account_id in targets:
            logger.info(f"Processing: {p_name} (ID: {p_id}, SellerProductID: {seller_product_id}, NewPrice: {selling_price})")
            
            if account_id not in clients:
                account = session.get(MarketAccount, account_id)
                clients[account_id] = CoupangClient(
                    vendor_id=account.credentials.get("vendor_id"),
                    access_key=account.credentials.get("access_key"),
                    secret_key=account.credentials.get("secret_key")
                )
            
            client = clients[account_id]
            
            # 1. 상품 상세 정보를 조회하여 vendorItemId 확보
            code, detail = client.get_product(seller_product_id)
            if code != 200:
                logger.error(f"Failed to fetch product detail for {seller_product_id}. Code: {code}")
                continue
                
            items = detail.get("data", {}).get("items", [])
            if not items:
                logger.error(f"No items found for product {seller_product_id}")
                continue
                
            # 여러 아이템(옵션)이 있을 수 있으나, 현재 단일 아이템 구조 가정
            for item in items:
                v_id = item.get("vendorItemId")
                if not v_id:
                    continue
                
                # 2. 가격 업데이트 (판매가 + 배송비 합산 기준)
                # 실제 CoupangSync 로직에서는 배송비를 포함하지만, 여기서는 단순화를 위해 DB selling_price를 사용
                # (normalize_product_prices.py에서 이미 배송비와 마진이 합산된 값이 selling_price에 들어감)
                
                price_to_set = (selling_price // 10) * 10
                if price_to_set < 3000:
                    price_to_set = 3000
                    
                up_code, up_resp = client.update_price(str(v_id), price_to_set)
                logger.info(f"Price update for vendor_item {v_id} to {price_to_set}: {up_code}")
                
                # 3. 판매 재개
                res_code, res_resp = client.resume_sales(str(v_id))
                logger.info(f"Resume sales for vendor_item {v_id}: {res_code}")

            # 4. DB 상태 복구
            session.execute(
                update(MarketListing)
                .where(MarketListing.market_item_id == seller_product_id)
                .values(status="ACTIVE", coupang_status="IN_REVIEW") # 다시 심사 상태로
            )

        session.commit()
        logger.info("Price sync and resume process completed.")

if __name__ == "__main__":
    resume_and_update_prices()
