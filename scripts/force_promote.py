import asyncio
import uuid
import logging
from app.session_factory import session_factory
from app.models import SupplierItemRaw, SourcingCandidate
from app.services.sourcing_service import SourcingService
from sqlalchemy import select, text
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def force_promote(keyword):
    with session_factory() as s:
        service = SourcingService(s)
        stmt = select(SupplierItemRaw).where(text("raw::text ilike :kw")).params(kw=f"%{keyword}%")
        items = s.execute(stmt).scalars().all()
        print(f"Found {len(items)} items for '{keyword}' in Raw.")
        
        count = 0
        for it in items:
            # Check if already exists in Candidate
            exists = s.execute(select(SourcingCandidate).where(SourcingCandidate.supplier_item_id == it.item_code)).first()
            if exists:
                continue
            
            raw = it.raw if isinstance(it.raw, dict) else {}
            supply_price = raw.get("supply_price") or raw.get("supplyPrice") or raw.get("fixedPrice") or raw.get("price") or 0
            
            # Simplified candidate creation for forced promotion
            candidate = SourcingCandidate(
                supplier_code=it.supplier_code,
                supplier_item_id=it.item_code,
                name=raw.get("item_name") or raw.get("name") or "Unknown",
                supply_price=int(supply_price) if supply_price else 0,
                source_strategy="FORCE_PROMOTE",
                status="PENDING",
                thumbnail_url=raw.get("thumbnail_url") or raw.get("imageUrl") or (raw.get("images")[0] if raw.get("images") else None)
            )
            s.add(candidate)
            count += 1
        
        s.commit()
        print(f"Promoted {count} items to PENDING.")

if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else "겨울"
    asyncio.run(force_promote(kw))
