import uuid
import logging
from app.db import SessionLocal
from app.models import Product, MarketAccount
from app.coupang_sync import register_product

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_reg(product_id_str=None):
    session = SessionLocal()
    try:
        if product_id_str:
            product = session.get(Product, uuid.UUID(product_id_str))
        else:
            product = session.query(Product).filter(Product.processing_status == 'COMPLETED').first()
            
        if not product:
            logger.error("No product found to test")
            return

        # Get the Coupang account
        account = session.query(MarketAccount).filter(MarketAccount.market_code == 'COUPANG', MarketAccount.is_active == True).first()
        if not account:
            logger.error("No active Coupang account found")
            return

        logger.info(f"Testing registration for Product ID: {product.id} on Account: {account.name}")
        
        # register_product(session, account_id, product_id)
        success, message = register_product(session, account.id, product.id)
        
        if success:
            logger.info(f"Registration SUCCESS: {message}")
        else:
            logger.error(f"Registration FAILED: {message}")
            
    except Exception as e:
        logger.exception(f"Unexpected error during test: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    import sys
    p_id = sys.argv[1] if len(sys.argv) > 1 else None
    test_reg(p_id)
