import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select

from app.db import SessionLocal
from app.models import Product, MarketRegistrationRetry, SupplierRawFetchLog


def _format_reason(reason: str | None) -> str:
    if not reason:
        return "-"
    s = str(reason).replace("\n", " ").strip()
    return s[:160]


def main() -> int:
    parser = argparse.ArgumentParser(description="Report Coupang gating status and fallbacks")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, args.days))

    with SessionLocal() as session:
        doc_pending = session.scalars(
            select(Product)
            .where(Product.coupang_doc_pending.is_(True))
            .order_by(Product.updated_at.desc())
            .limit(args.limit)
        ).all()

        retry_rows = session.scalars(
            select(MarketRegistrationRetry)
            .where(MarketRegistrationRetry.market_code == "COUPANG")
            .where(MarketRegistrationRetry.status.in_(["queued", "failed"]))
            .order_by(MarketRegistrationRetry.updated_at.desc())
            .limit(args.limit)
        ).all()

        skip_logs = session.scalars(
            select(SupplierRawFetchLog)
            .where(SupplierRawFetchLog.supplier_code == "COUPANG")
            .where(SupplierRawFetchLog.endpoint == "register_product_skipped")
            .where(SupplierRawFetchLog.fetched_at >= cutoff)
            .order_by(SupplierRawFetchLog.fetched_at.desc())
            .limit(args.limit)
        ).all()

    print("=== Coupang Doc Pending Products ===")
    print(f"count: {len(doc_pending)}")
    for product in doc_pending:
        print(
            f"- {product.id} | {product.brand or '-'} | {product.name[:60]} | {product.coupang_doc_pending_reason or '-'}"
        )

    print("\n=== Coupang Registration Retries ===")
    print(f"count: {len(retry_rows)}")
    for row in retry_rows:
        print(
            f"- {row.product_id} | status={row.status} attempts={row.attempts} | {_format_reason(row.reason)}"
        )

    print("\n=== Recent Coupang Skip Logs ===")
    print(f"since: {cutoff.isoformat()} | count: {len(skip_logs)}")
    reason_counter = Counter()
    for log in skip_logs:
        msg = None
        if isinstance(log.response_payload, dict):
            msg = log.response_payload.get("message")
        reason = _format_reason(msg)
        reason_counter[reason] += 1
        product_id = None
        if isinstance(log.request_payload, dict):
            product_id = log.request_payload.get("productId")
        print(f"- {log.fetched_at.isoformat()} | product={product_id} | {reason}")

    if reason_counter:
        print("\nTop skip reasons:")
        for reason, count in reason_counter.most_common(10):
            print(f"- {count} | {reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
