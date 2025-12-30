import argparse
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.models import MarketAccount, Product
from app.services.market_service import MarketService
from app.services.sync_scheduler_state import update_scheduler_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry Coupang registrations for doc_pending products")
    parser.add_argument("--limit", type=int, default=50, help="Max products to retry")
    parser.add_argument("--dry-run", action="store_true", help="List targets without registering")
    args = parser.parse_args()

    update_scheduler_state(
        "coupang_doc_pending_retry",
        "running",
        {"limit": args.limit, "dry_run": args.dry_run},
    )

    processed = 0
    succeeded = 0
    skipped = 0
    failed = 0

    with SessionLocal() as session:
        account = (
            session.query(MarketAccount)
            .filter(MarketAccount.market_code == "COUPANG")
            .filter(MarketAccount.is_active.is_(True))
            .first()
        )
        if not account:
            update_scheduler_state("coupang_doc_pending_retry", "failed", {"error": "account not found"})
            print("No active COUPANG account found.")
            return 1

        products = session.scalars(
            select(Product)
            .where(Product.coupang_doc_pending.is_(True))
            .order_by(Product.updated_at.desc())
            .limit(args.limit)
        ).all()

        if args.dry_run:
            for product in products:
                print(f"- {product.id} | {product.brand or '-'} | {product.name[:60]}")
            update_scheduler_state(
                "coupang_doc_pending_retry",
                "completed",
                {"processed": 0, "dry_run_count": len(products)},
            )
            return 0

        service = MarketService(session)
        for product in products:
            processed += 1
            result = service.register_product("COUPANG", account.id, product.id)
            status = (result.get("status") or "").lower()
            if status == "success":
                succeeded += 1
            elif status == "skipped":
                skipped += 1
            else:
                failed += 1

    summary = {
        "processed": processed,
        "succeeded": succeeded,
        "skipped": skipped,
        "failed": failed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    update_scheduler_state("coupang_doc_pending_retry", "completed", summary)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
