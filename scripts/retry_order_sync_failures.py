import argparse
from app.db import SessionLocal
from app.services.order_sync_retry import list_failed_coupang_sync_log_ids, retry_coupang_failures
from app.services.sync_scheduler_state import update_scheduler_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry failed Coupang order sync logs")
    parser.add_argument("--limit", type=int, default=200, help="Max failures to retry")
    parser.add_argument("--retry-count", type=int, default=1, help="Retry attempts per log")
    args = parser.parse_args()

    update_scheduler_state("order_sync_retry", "running", {"limit": args.limit, "retry_count": args.retry_count})
    with SessionLocal() as session:
        ids = list_failed_coupang_sync_log_ids(session, limit=args.limit)
        result = retry_coupang_failures(session, ids, retry_count=args.retry_count)
        update_scheduler_state("order_sync_retry", "completed", result)
        print(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
