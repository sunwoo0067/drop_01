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
    db.close()
    
    # 2. PENDING 상태의 후보들 중 고득점 상품 승인 (모든 PENDING 대상)
    db = SessionLocal()
    stmt = (
        select(SourcingCandidate)
        .where(SourcingCandidate.status == "PENDING")
    )
    candidates = db.scalars(stmt).all()
    db.close()
    
    print(f"Found {len(candidates)} pending candidates. Starting parallel approval...")
    
    semaphore = asyncio.Semaphore(10) # 10개씩 병렬 처리
    approved_count = 0
    
    async def approve_with_session(candidate_id):
        nonlocal approved_count
        async with semaphore:
            # 각 태스크마다 별도의 세션 생성 (스레드/비동기 안전)
            task_db = SessionLocal()
            try:
                task_service = SourcingService(task_db)
                await task_service.approve_candidate(candidate_id)
                approved_count += 1
                if approved_count % 50 == 0:
                    print(f"Approved {approved_count}/{len(candidates)}...")
            finally:
                task_db.close()

    tasks = [approve_with_session(c.id) for c in candidates]
    await asyncio.gather(*tasks)
            
    print(f"Final: {approved_count} candidates processed.")

if __name__ == "__main__":
    asyncio.run(main())
