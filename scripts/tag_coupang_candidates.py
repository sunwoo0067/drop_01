import argparse
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Product
from app.services.coupang_candidate_policy import decide_coupang_eligibility


def main() -> int:
    parser = argparse.ArgumentParser(description="Tag Coupang eligibility for products")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--only-unknown", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as session:
        stmt = select(Product).order_by(Product.updated_at.desc()).limit(args.limit)
        if args.only_unknown:
            stmt = stmt.where(Product.coupang_eligibility == "UNKNOWN")

        products = session.scalars(stmt).all()
        updated = 0
        for product in products:
            eligibility, reasons = decide_coupang_eligibility(session, product)
            if args.dry_run:
                print(f"{product.id} -> {eligibility} ({','.join(reasons) if reasons else '-'})")
                continue
            if product.coupang_eligibility != eligibility:
                product.coupang_eligibility = eligibility
                updated += 1
        if not args.dry_run:
            session.commit()
            print(
                f"updated={updated} total={len(products)} at {datetime.now(timezone.utc).isoformat()}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
