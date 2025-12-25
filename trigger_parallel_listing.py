import asyncio
import logging
from sqlalchemy import select
from app.db import get_session
from app.models import MarketAccount, Product
from app.session_factory import session_factory
from app.services.market_service import MarketService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def trigger_parallel_listing():
    logger.info("Starting Parallel Market Listing for COMPLETED products...")
    
    session_gen = get_session()
    db = next(session_gen)
    
    try:
        # 1. 활성 계정 조회
        stmt_acc = select(MarketAccount).where(MarketAccount.is_active == True)
        accounts = db.scalars(stmt_acc).all()
        if not accounts:
            logger.error("No active market accounts found.")
            return

        # 2. 가공 완료된 상품 조회 (최대 15,000건)
        stmt_prod = select(Product).where(Product.processing_status == "COMPLETED").order_by(Product.updated_at.desc()).limit(15000)
        products = db.scalars(stmt_prod).all()
        if not products:
            logger.info("No COMPLETED products found for listing.")
            return

        logger.info(f"Found {len(products)} products ready for listing across {len(accounts)} accounts.")

        # 3. 병렬 등록 세마포어 (마켓 API 부하 조절)
        # Naver의 엄격한 속도 제한을 위해 세마포어를 2로 축소
        register_sem = asyncio.Semaphore(2)

        async def _register_task(idx, p_id):
            async with register_sem:
                # 독립 세션 사용
                with session_factory() as tmp_db:
                    m_service = MarketService(tmp_db)
                    target_acc = accounts[idx % len(accounts)]
                    market_code = target_acc.market_code
                    
                    try:
                        # 상품 상태 확인 (중복 등록 방지 로직)
                        p = tmp_db.get(Product, p_id)
                        if not p or p.processing_status != "COMPLETED":
                            return False
                        
                        logger.info(f"Registering Product {p_id} to {market_code} ({target_acc.name})...")
                        
                        # 네이버의 경우 특히 API Rate Limit이 엄격하므로 추가 지연
                        if market_code == "SMARTSTORE":
                            # Naver has strict rate limits, wait longer
                            await asyncio.sleep(10.0)
                            
                        res = m_service.register_product(market_code, target_acc.id, p.id)
                        
                        success = res.get("status") == "success"
                        if success:
                            logger.info(f"SUCCESS: Product {p_id} listed on {market_code}")
                        else:
                            logger.error(f"FAIL: Product {p_id} on {market_code}: {res.get('message')}")
                        return success
                    except Exception as e:
                        logger.error(f"Async listing error for product {p_id}: {e}")
                        return False

        # 테스크 생성 (계정별 라운드 로빈 배분)
        tasks = [_register_task(i, p.id) for i, p in enumerate(products)]
        results = await asyncio.gather(*tasks)
        
        success_count = sum(1 for r in results if r)
        logger.info(f"Parallel listing completed: {success_count}/{len(products)} products registered successfully.")

    except Exception as e:
        logger.exception(f"Fatal error during parallel listing: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(trigger_parallel_listing())
