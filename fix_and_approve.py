import asyncio
import logging
from sqlalchemy import select
from app.db import SessionLocal
from app.models import SourcingCandidate, Product, SupplierItemRaw
from app.services.sourcing_service import SourcingService

logging.basicConfig(level=logging.INFO)

async def main():
    db = SessionLocal()
    service = SourcingService(db)
    
    # APPROVED 상태이지만 Product가 없는 후보군 조회
    stmt = (
        select(SourcingCandidate)
        .where(SourcingCandidate.status == 'APPROVED')
        .limit(1000)
    )
    candidates = db.scalars(stmt).all()
    print(f"Syncing {len(candidates)} approved candidates to products...")
    
    for c in candidates:
        try:
            # 수정된 approve_candidate 호출
            await service.approve_candidate(c.id)
        except Exception as e:
            pass
            
    db.commit()
    
    print(f"Current Products: {db.execute(select(select(Product).count())).scalar()}")
    db.close()

if __name__ == "__main__":
    asyncio.run(main())
