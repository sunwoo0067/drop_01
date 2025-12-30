
import asyncio
import logging
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.services.orchestrator_service import OrchestratorService
from app.services.sourcing_service import SourcingService
from app.models import Product, SourcingCandidate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("demo_combination")

async def run_demo_sourcing():
    db = SessionLocal()
    orchestrator = OrchestratorService(db)
    sourcing = SourcingService(db)
    
    try:
        # 1. 특정 키워드로 소싱 트리거
        keyword = "텀블러"
        logger.info(f"Step 1: Sourcing products for keyword '{keyword}'...")
        await sourcing.execute_keyword_sourcing(keyword, limit=5)
        
        # 2. 상위 점수 후보 선별 및 승인
        logger.info("Step 2: Approving candidates and creating products with options...")
        candidates = db.query(SourcingCandidate).filter_by(status="PENDING").limit(3).all()
        for cand in candidates:
            # 개선된 approve_candidate 호출 (실시간 옵션 페칭 포함)
            await sourcing.approve_candidate(cand.id)
            
        # 3. 가공 및 등록 (병렬 실행)
        logger.info("Step 3: Processing and registering to marketplaces...")
        # 가공 수행 (이미지 및 SEO)
        from app.services.processing_service import ProcessingService
        processor = ProcessingService(db)
        await processor.process_pending_products(limit=3)
        
        # 마켓 등록 수행
        from app.services.market_service import MarketService
        market = MarketService(db)
        
        # DRAFT 상태인 상품들 조회
        products = db.query(Product).filter_by(status="DRAFT", processing_status="COMPLETED").limit(3).all()
        for p in products:
            logger.info(f"Registering product '{p.name}' (Options: {len(p.options)})")
            # 모든 활성 마켓에 등록 시도
            await market.register_product_to_all_active_markets(p.id)
            
        logger.info("Demo combination upload task finished.")

    except Exception as e:
        logger.error(f"Demo error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run_demo_sourcing())
