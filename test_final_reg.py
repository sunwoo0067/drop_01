import asyncio
import logging
import uuid
from sqlalchemy import select
from app.db import get_session
from app.models import MarketAccount, Product
from app.services.market_service import MarketService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_registration():
    session_gen = get_session()
    session = next(session_gen)
    market_service = MarketService(session)
    
    stmt = select(MarketAccount).where(MarketAccount.is_active == True)
    accounts = session.scalars(stmt).all()
    
    stmt_completed = select(Product).where(Product.processing_status == "COMPLETED").order_by(Product.updated_at.desc()).limit(1)
    product = session.scalars(stmt_completed).first()
    
    if not product:
        logger.error("No COMPLETED products found.")
        return

    logger.info(f"Target Product: {product.processed_name or product.name}")
    
    for account in accounts:
        logger.info(f"Registering to Market: {account.market_code}, Account: {account.name}...")
        try:
            result = market_service.register_product(account.market_code, account.id, product.id)
            if result.get("status") == "success":
                logger.info(f"SUCCESS: {result.get('message')}")
            else:
                logger.error(f"FAILED: {result.get('message')}")
        except Exception as e:
            logger.error(f"Error during registration: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_registration())
