import asyncio
import logging
import uuid
from sqlalchemy import select
from app.db import get_session
from app.models import MarketAccount, Product
from app.services.sourcing_service import SourcingService
from app.services.processing_service import ProcessingService
from app.services.market_service import MarketService

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_automation():
    # 1. 초기화
    session_gen = get_session()
    session = next(session_gen)
    
    sourcing_service = SourcingService(session)
    processing_service = ProcessingService(session)
    market_service = MarketService(session)
    
    # 2. 활성 계정 확인
    stmt = select(MarketAccount).where(MarketAccount.is_active == True)
    accounts = session.scalars(stmt).all()
    
    if not accounts:
        logger.error("No active market accounts found. Please activate at least one account.")
        return

    logger.info(f"Active accounts found: {[(a.market_code, a.name) for a in accounts]}")
    
    # 3. 신규 상품 소싱 (가습기 - 겨울 트렌드)
    # execute_expanded_sourcing을 사용하여 AI가 키워드를 확장하여 소싱하도록 함
    keyword = "가습기"
    logger.info(f"Step 1: Sourcing new products for keyword '{keyword}'...")
    try:
        # 소싱 서비스 실행
        await sourcing_service.execute_expanded_sourcing(keyword)
        logger.info("Sourcing completed.")
    except Exception as e:
        logger.error(f"Error during sourcing: {e}")

    # 4. 가공 대기 중인 상품 가져오기 및 가공 (최대 3개)
    # 소싱에서 갓 뽑은 것들 또는 이미 PENDING 상태인 것들
    logger.info("Step 2: Processing (SEO Optimization) for pending products...")
    processed_count = await processing_service.process_pending_products(limit=3)
    logger.info(f"Successfully processed {processed_count} products.")

    if processed_count == 0:
        logger.warning("No products were processed. Checking if there are COMPLETED products already...")
    
    # 5. 가공 완료(COMPLETED)된 상품을 모든 활성 계정에 등록
    stmt_completed = select(Product).where(Product.processing_status == "COMPLETED").order_by(Product.updated_at.desc()).limit(3)
    products_to_register = session.scalars(stmt_completed).all()
    
    if not products_to_register:
        logger.error("No COMPLETED products found to register.")
        return

    logger.info(f"Step 3: Registering {len(products_to_register)} products to {len(accounts)} accounts...")
    
    for product in products_to_register:
        logger.info(f"--- Product: {product.processed_name or product.name} ---")
        for account in accounts:
            logger.info(f"Registering to Market: {account.market_code}, Account: {account.name}...")
            try:
                result = market_service.register_product(account.market_code, account.id, product.id)
                if result.get("status") == "success":
                    logger.info(f"SUCCESS: {result.get('message')}")
                else:
                    logger.error(f"FAILED: {result.get('message')}")
            except Exception as e:
                logger.error(f"Error during registration: {e}")

    logger.info("Automation workflow finished.")

if __name__ == "__main__":
    asyncio.run(run_automation())
