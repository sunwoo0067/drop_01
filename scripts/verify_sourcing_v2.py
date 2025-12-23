import asyncio
import logging
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.services.sourcing_service import SourcingService
from app.models import BenchmarkProduct, SourcingCandidate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_sourcing_high_level():
    db: Session = SessionLocal()
    try:
        sourcing_service = SourcingService(db)
        
        # 1. 테스트용 벤치마크 상품 확인
        stmt = select(BenchmarkProduct).order_by(BenchmarkProduct.created_at.desc()).limit(1)
        benchmark = db.execute(stmt).scalar_one_or_none()
        
        if not benchmark:
            logger.error("테스트할 벤치마크 상품이 없습니다.")
            return

        # 검색 범용성을 위해 이름 단순화 (테스트용)
        original_name = benchmark.name
        simple_name = "캠핑의자" if "맛밤" not in original_name else "맛밤"
        benchmark.name = simple_name # 임시 변경
        
        logger.info(f"--- 검증 시작: {simple_name} (Original: {original_name[:30]}...) ---")
        
        # 2. 고도화된 소싱 실행
        await sourcing_service.execute_benchmark_sourcing(benchmark.id)
        
        # 3. 결과 확인
        stmt_cand = select(SourcingCandidate).where(SourcingCandidate.benchmark_product_id == benchmark.id).order_by(SourcingCandidate.final_score.desc())
        candidates = db.scalars(stmt_cand).all()
        
        logger.info(f"검출된 후보 수: {len(candidates)}")
        
        for cand in candidates[:5]:
            logger.info(f"후보: {cand.name}")
            logger.info(f"  - 전략: {cand.source_strategy}")
            logger.info(f"  - 최종 점수: {cand.final_score}")
            logger.info(f"  - 시각적 분석 존재 여부: {'Yes' if cand.visual_analysis else 'No'}")
            
        if any(cand.visual_analysis for cand in candidates):
            logger.info("✅ SUCCESS: 시각적 분석 결과가 DB에 저장되었습니다.")
        
        # 벤치마크 이름 복구
        benchmark.name = original_name

    except Exception as e:
        logger.exception(f"검증 중 오류 발생: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(verify_sourcing_high_level())
