import os
import uuid
import logging
from sqlalchemy import select, update
from app.db import get_session
from app.models import Product, MarketListing, MarketAccount
from app.coupang_client import CoupangClient
from app.session_factory import session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def emergency_stop_sales():
    with session_factory() as session:
        # 1. 대상 상품 식별 (selling_price가 0인 최근 등록 상품)
        stmt = (
            select(Product.id, Product.name, MarketListing.market_item_id, MarketListing.market_account_id)
            .join(MarketListing, Product.id == MarketListing.product_id)
            .where(Product.selling_price == 0)
        )
        targets = session.execute(stmt).all()
        
        if not targets:
            logger.info("No targets found with selling_price = 0 and market listing.")
            return

        logger.info(f"Found {len(targets)} targets for emergency stop.")

        # Account ID별로 Client 캐싱
        clients = {}

        for p_id, p_name, seller_product_id, account_id in targets:
            logger.info(f"Processing: {p_name} (ID: {p_id}, SellerProductID: {seller_product_id})")
            
            if account_id not in clients:
                account = session.get(MarketAccount, account_id)
                if not account:
                    logger.error(f"Account {account_id} not found.")
                    continue
                
                # MarketAccount의 credentials 필드명은 snake_case임
                clients[account_id] = CoupangClient(
                    vendor_id=account.credentials.get("vendor_id"),
                    access_key=account.credentials.get("access_key"),
                    secret_key=account.credentials.get("secret_key")
                )
            
            client = clients[account_id]
            
            # 쿠팡 API로 삭제 시도
            code, resp = client.delete_product(seller_product_id)
            if code == 200 or code == 204:
                logger.info(f"Successfully deleted/stopped product {seller_product_id} from Coupang.")
                # DB 상태 업데이트
                session.execute(
                    update(MarketListing)
                    .where(MarketListing.market_item_id == seller_product_id)
                    .values(status="DELETED", coupang_status="DELETED")
                )
            else:
                logger.warning(f"Failed to delete product {seller_product_id}. Code: {code}, Resp: {resp}")
                # 삭제가 안 되면 판매중지라도 시도
                get_code, detail = client.get_product(seller_product_id)
                if get_code == 200:
                    items = detail.get("data", {}).get("items", [])
                    for item in items:
                        v_id = item.get("vendorItemId")
                        if v_id:
                            stop_code, stop_resp = client.stop_sales(str(v_id))
                            logger.info(f"Stop sales for vendor_item {v_id}: {stop_code}")
                else:
                    logger.error(f"Could not even fetch product detail for {seller_product_id}")

        session.commit()
        logger.info("Emergency stop sales process completed.")

if __name__ == "__main__":
    emergency_stop_sales()
