import sys
import asyncio
from sqlalchemy import select, func
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import SupplierItemRaw, Product, SourcingCandidate
from app.services.sourcing_service import SourcingService
from app.settings import settings

engine = create_engine(settings.market_database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

async def main():
    print("Starting import of 5,000 items from raw...")
    db = SessionLocal()
    service = SourcingService(db)
    
    # 1. 5,000건의 SourcingCandidate 생성
    count = service.import_from_raw(limit=5000)
    print(f"Imported {count} items as SourcingCandidates.")
    
    # 2. PENDING 상태의 후보들 중 고득점 상품 5,0000건 승인
    # (import_from_raw는 기본 점수 50.0을 주므로, 강제 승인 로직 수행)
    stmt = (
        select(SourcingCandidate)
        .where(SourcingCandidate.status == "PENDING")
        .limit(5000)
    )
    candidates = db.scalars(stmt).all()
    
    approved_count = 0
    for c in candidates:
        await service.approve_candidate(c.id)
        approved_count += 1
        if approved_count % 100 == 0:
            print(f"Approved {approved_count}/5000...")
            
    print(f"Final: {approved_count} products added to PENDING queue.")
    db.close()

if __name__ == "__main__":
    asyncio.run(main())
