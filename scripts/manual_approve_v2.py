import asyncio
import uuid
import logging
from sqlalchemy import select
from app.db import SessionLocal
from app.models import SourcingCandidate, Product
from app.services.sourcing_service import SourcingService

logging.basicConfig(level=logging.INFO)

async def main():
    db = SessionLocal()
    service = SourcingService(db)
    
    # PENDING 중 점수 높은 순 1000건 시도
    stmt = (
        select(SourcingCandidate)
        .where(SourcingCandidate.status == "PENDING")
        .order_by(SourcingCandidate.final_score.desc())
        .limit(1000)
    )
    candidates = db.scalars(stmt).all()
    print(f"Found {len(candidates)} candidates.")
    
    for c in candidates:
        try:
            # approve_candidate 내부에서 product 생성 및 commit 수행함
            await service.approve_candidate(c.id)
        except Exception as e:
            print(f"Error approving {c.id}: {e}")
            
    db.commit() # 최종 확인용
    
    # 확인
    prod_count = db.execute(select(select(Product).count())).scalar()
    print(f"Total products now: {prod_count}")
    db.close()

if __name__ == "__main__":
    asyncio.run(main())
