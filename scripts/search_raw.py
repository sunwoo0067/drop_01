from app.session_factory import session_factory
from app.models import SupplierItemRaw
from sqlalchemy import select, text
import sys

def main():
    kw = sys.argv[1] if len(sys.argv) > 1 else "겨울"
    with session_factory() as s:
        # PostgreSQL syntax for JSONB search or cast
        stmt = select(SupplierItemRaw).where(text("raw::text ilike :kw")).params(kw=f"%{kw}%").limit(10)
        items = s.execute(stmt).scalars().all()
        print(f"Results for '{kw}' in SupplierItemRaw:")
        for it in items:
            raw = it.raw if isinstance(it.raw, dict) else {}
            name = raw.get("item_name") or raw.get("name") or "Unknown"
            print(f" - {name} (ID: {it.id})")

if __name__ == "__main__":
    main()
