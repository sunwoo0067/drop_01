import logging
from sqlalchemy import select, delete
from app.db import get_session
from app.models import MarketAccount, Product, MarketListing

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup_orphans():
    session_gen = get_session()
    db = next(session_gen)
    
    try:
        # 1. 활성 계정 ID 목록 가져오기
        stmt_active_acc = select(MarketAccount.id).where(MarketAccount.is_active == True)
        active_account_ids = db.scalars(stmt_active_acc).all()
        logger.info(f"Active Account IDs: {active_account_ids}")

        # 2. 유효한 리스팅(활성 계정에 속한 리스팅)이 있는 상품 ID 목록
        stmt_valid_product_ids = select(MarketListing.product_id).where(MarketListing.market_account_id.in_(active_account_ids))
        valid_product_ids = set(db.scalars(stmt_valid_product_ids).all())
        logger.info(f"Products with active listings: {len(valid_product_ids)}")

        # 3. 비활성 계정 리스팅 삭제
        stmt_inactive_listings = delete(MarketListing).where(~MarketListing.market_account_id.in_(active_account_ids))
        res_del_listings = db.execute(stmt_inactive_listings)
        logger.info(f"Deleted inactive MarketListings: {res_del_listings.rowcount}")

        # 4. 활성 계정에 리스팅되지 않은 모든 상품 삭제 ( Aggressive Cleanup )
        # 사용자의 '현재 활성화된 계정만 남기고 디비에서 삭제해줘' 요청에 따름
        # 만약 PENDING 이나 COMPLETED 상태의 상품도 모두 삭제하길 원하는 것이라면 아래 로직 적용
        stmt_orphan_products = delete(Product).where(~Product.id.in_(list(valid_product_ids)))
        res_del_products = db.execute(stmt_orphan_products)
        logger.info(f"Deleted unlisted Products: {res_del_products.rowcount}")

        db.commit()
        logger.info("Cleanup completed and committed.")

    except Exception as e:
        db.rollback()
        logger.error(f"Error during cleanup: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_orphans()
