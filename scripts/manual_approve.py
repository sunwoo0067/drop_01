import asyncio
import uuid
from sqlalchemy import select
from app.db import SessionLocal
from app.models import SourcingCandidate
from app.services.sourcing_service import SourcingService

async def main():
    db = SessionLocal()
    service = SourcingService(db)
    
    # 5,000건 강제 승인
    stmt = (
        select(SourcingCandidate)
        .where(SourcingCandidate.status == "PENDING")
        .order_by(SourcingCandidate.created_at.desc())
        .limit(5000)
    )
    candidates = db.scalars(stmt).all()
    print(f"Approving {len(candidates)} candidates manually...")
    
    for c in candidates:
        try:
            await service.approve_candidate(c.id)
        except Exception as e:
            print(f"Error: {e}")
    db.close()

if __name__ == "__main__":
    asyncio.run(main())
