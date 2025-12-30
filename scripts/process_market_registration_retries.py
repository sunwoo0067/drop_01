import argparse
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.models import MarketAccount, MarketRegistrationRetry
from app.services.market_service import MarketService
from app.services.sync_scheduler_state import update_scheduler_state


def _pick_account(session, market_code: str, account_id: str | None) -> MarketAccount | None:
    if account_id:
        try:
            account_uuid = uuid.UUID(account_id)
        except ValueError:
            return None
        account = session.get(MarketAccount, account_uuid)
        if account and account.market_code == market_code:
            return account
        return None

    return (
        session.query(MarketAccount)
        .filter(MarketAccount.market_code == market_code)
        .filter(MarketAccount.is_active.is_(True))
        .first()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Process queued market registration retries")
    parser.add_argument("--market", default="COUPANG", help="Market code (default: COUPANG)")
    parser.add_argument("--account-id", default=None, help="Override market account ID")
    parser.add_argument("--limit", type=int, default=50, help="Max retry rows to process")
    parser.add_argument("--max-attempts", type=int, default=3, help="Max attempts before marking failed")
    parser.add_argument("--include-failed", action="store_true", help="Retry rows in failed status")
    args = parser.parse_args()

    market_code = str(args.market or "").strip().upper() or "COUPANG"
    max_attempts = max(1, int(args.max_attempts))

    update_scheduler_state(
        "market_registration_retry",
        "running",
        {
            "market": market_code,
            "limit": args.limit,
            "max_attempts": max_attempts,
            "include_failed": args.include_failed,
        },
    )

    processed = 0
    succeeded = 0
    skipped = 0
    failed = 0

    with SessionLocal() as session:
        account = _pick_account(session, market_code, args.account_id)
        if not account:
            update_scheduler_state("market_registration_retry", "failed", {"error": "account not found"})
            print("No active market account found.")
            return 1

        statuses = ["queued"]
        if args.include_failed:
            statuses.append("failed")

        rows = session.scalars(
            select(MarketRegistrationRetry)
            .where(MarketRegistrationRetry.market_code == market_code)
            .where(MarketRegistrationRetry.status.in_(statuses))
            .order_by(MarketRegistrationRetry.updated_at.asc())
            .limit(args.limit)
        ).all()

        service = MarketService(session)
        for row in rows:
            processed += 1
            if row.attempts >= max_attempts:
                row.status = "failed"
                row.reason = row.reason or "max attempts reached"
                session.commit()
                failed += 1
                continue

            row.status = "running"
            row.attempts += 1
            session.commit()

            result = service.register_product(market_code, account.id, row.product_id)
            status = (result.get("status") or "").lower()
            message = result.get("message") if isinstance(result, dict) else None

            if status == "success":
                row.status = "success"
                row.reason = None
                succeeded += 1
            elif status == "skipped":
                row.status = "skipped"
                row.reason = message
                skipped += 1
            else:
                row.reason = message
                if row.attempts >= max_attempts:
                    row.status = "failed"
                    failed += 1
                else:
                    row.status = "queued"

            session.commit()

    summary = {
        "processed": processed,
        "succeeded": succeeded,
        "skipped": skipped,
        "failed": failed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    update_scheduler_state("market_registration_retry", "completed", summary)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
