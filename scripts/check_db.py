from app.session_factory import session_factory
from app.models import BenchmarkProduct, SupplierSyncJob, MarketListing, SourcingCandidate, Product, SupplierItemRaw
from sqlalchemy import select, func

def check_benchmarks():
    with session_factory() as session:
        benchmarks = session.execute(select(BenchmarkProduct)).scalars().all()
        for b in benchmarks:
            print(f"Benchmark -> ID: {b.id}, Name: {b.name}")

def check_jobs():
    with session_factory() as session:
        jobs = session.execute(select(SupplierSyncJob).order_by(SupplierSyncJob.created_at.desc()).limit(5)).scalars().all()
        for j in jobs:
            print(f"Job -> ID: {j.id}, Status: {j.status}, Error: {j.last_error[:100] if j.last_error else 'None'}")

def check_market_listings():
    with session_factory() as session:
        listings = session.execute(select(MarketListing)).scalars().all()
        print(f"Total Market Listings: {len(listings)}")
        for l in listings:
            product = session.get(Product, l.product_id)
            p_name = product.name if product else "Unknown"
            print(f"Registered -> ID: {l.market_item_id}, Name: {p_name}")

def check_candidates():
    with session_factory() as session:
        results = session.execute(select(SourcingCandidate.status, func.count()).group_by(SourcingCandidate.status)).all()
        for status, count in results:
            print(f"Candidate Status[{status}]: {count}")

def search_candidates(keyword):
    with session_factory() as session:
        candidates = session.execute(
            select(SourcingCandidate)
            .where(SourcingCandidate.status == 'PENDING')
            .where(SourcingCandidate.name.like(f'%{keyword}%'))
            .limit(10)
        ).scalars().all()
        print(f"Search Results for '{keyword}':")
        for c in candidates:
            print(f" - {c.name}")

def check_raw():
    with session_factory() as session:
        items = session.execute(select(SupplierItemRaw).limit(10)).scalars().all()
        print(f"SupplierItemRaw Sample (first 10):")
        for it in items:
            raw = it.raw if isinstance(it.raw, dict) else {}
            name = raw.get("item_name") or raw.get("itemName") or raw.get("name") or "Unknown"
            print(f" - {name} (ID: {it.id})")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "raw":
            check_raw()
        else:
            search_candidates(sys.argv[1])
    else:
        check_benchmarks()
        print("-" * 20)
        check_jobs()
        print("-" * 20)
        check_market_listings()
        print("-" * 20)
        check_candidates()
        print("-" * 20)
        check_raw()
