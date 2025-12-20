import asyncio
import logging
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import SessionLocal
from app.models import BenchmarkProduct, SourcingCandidate
from app.services.sourcing_service import SourcingService
from app.services.ai.agents.sourcing_agent import SourcingAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_vector_sourcing():
    db: Session = SessionLocal()
    sourcing_service = SourcingService(db)
    sourcing_agent = SourcingAgent(db)

    try:
        # 1. 벤치마크 상품 확인
        benchmark = db.execute(select(BenchmarkProduct).limit(1)).scalar_one_or_none()
        if not benchmark:
            logger.error("No benchmark product found to test.")
            return

        logger.info(f"Testing with Benchmark: {benchmark.name} (ID: {benchmark.id})")
        
        # 2. SourcingAgent 실행 (Hybrid Search 테스트)
        logger.info("\n--- 1. Testing SourcingAgent Hybrid Search ---")
        input_data = {
            "name": benchmark.name,
            "detail_html": benchmark.detail_html,
            "price": benchmark.price
        }
        
        # Search Node 직접 테스트 (내부 로직 확인용)
        state = {
            "target_id": str(benchmark.id),
            "benchmark_data": input_data,
            "collected_items": []
        }
        search_result = sourcing_agent.search_supplier(state)
        logger.info(f"Hybrid Search Result Logs: {search_result.get('logs')}")
        logger.info(f"Merged items count: {len(search_result.get('collected_items', []))}")

        # 3. SourcingService._create_candidate 테스트 (Rich Embedding & Similarity)
        logger.info("\n--- 2. Testing Rich Candidate Creation ---")
        test_item = {
            "item_code": "test_v123",
            "name": f"유사 상품 - {benchmark.name}",
            "supply_price": 10000,
            "thumbnail_url": benchmark.image_urls[0] if benchmark.image_urls else None
        }
        
        await sourcing_service._create_candidate(
            test_item,
            strategy="VECTOR_TEST",
            benchmark_id=benchmark.id
        )
        
        # 생성된 후보 확인
        candidate = db.execute(
            select(SourcingCandidate)
            .where(SourcingCandidate.supplier_item_id == "test_v123")
        ).scalar_one_or_none()
        
        if candidate:
            logger.info(f"Candidate created with similarity score: {candidate.similarity_score}")
            if candidate.embedding is not None:
                logger.info(f"Candidate has embedding (Dim: {len(candidate.embedding)})")
            else:
                logger.error("Candidate embedding is missing!")
        else:
            logger.error("Failed to create test candidate.")

    except Exception as e:
        logger.exception(f"Error during vector sourcing test: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_vector_sourcing())
