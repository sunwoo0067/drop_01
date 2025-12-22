from __future__ import annotations

from typing import Any
import time

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from app.coupang_client import CoupangClient
from app.models import MarketAccount, SupplierRawFetchLog


def get_coupang_client_from_account(account: MarketAccount) -> CoupangClient:
    creds = account.credentials if isinstance(account.credentials, dict) else {}
    access_key = str(creds.get("access_key", "") or "").strip()
    secret_key = str(creds.get("secret_key", "") or "").strip()
    vendor_id = str(creds.get("vendor_id", "") or "").strip()
    return CoupangClient(
        access_key=access_key,
        secret_key=secret_key,
        vendor_id=vendor_id,
    )


def list_failed_coupang_sync_log_ids(session: Session, limit: int = 200) -> list[str]:
    endpoints = ["coupang/upload_invoices", "coupang/cancel_order"]
    stmt = (
        select(SupplierRawFetchLog.id)
        .where(SupplierRawFetchLog.supplier_code == "coupang")
        .where(SupplierRawFetchLog.endpoint.in_(endpoints))
        .where(or_(SupplierRawFetchLog.error_message.is_not(None), SupplierRawFetchLog.http_status >= 300))
        .order_by(SupplierRawFetchLog.fetched_at.desc())
        .limit(limit)
    )
    return [str(row[0]) for row in session.execute(stmt).all()]


def retry_coupang_failures(
    session: Session,
    ids: list[str],
    retry_count: int = 0,
) -> dict[str, int]:
    attempts = max(1, int(retry_count or 0)) + 1
    if not ids:
        return {"processed": 0, "succeeded": 0, "failed": 0}

    logs = session.scalars(
        select(SupplierRawFetchLog).where(SupplierRawFetchLog.id.in_(ids))
    ).all()

    succeeded = 0
    failed = 0

    for log in logs:
        if not log.account_id:
            failed += 1
            continue
        account = session.get(MarketAccount, log.account_id)
        if not account:
            failed += 1
            continue

        client = get_coupang_client_from_account(account)
        request_payload = log.request_payload if isinstance(log.request_payload, dict) else {}

        ok = False
        code = 0
        resp: dict[str, Any] | None = None
        for attempt in range(1, attempts + 1):
            if log.endpoint == "coupang/upload_invoices":
                code, resp = client.upload_invoices([request_payload])
                resp = resp if isinstance(resp, dict) else {"_raw": resp}
                data = resp.get("data") if isinstance(resp, dict) else None
                response_code = data.get("responseCode") if isinstance(data, dict) else None
                ok = code < 300 and response_code in (0, None)
            elif log.endpoint == "coupang/cancel_order":
                vendor_item_ids = request_payload.get("vendorItemIds") or []
                receipt_counts = request_payload.get("receiptCounts") or []
                user_id = request_payload.get("userId") or ""
                order_id = request_payload.get("orderId") or ""
                code, resp = client.cancel_order(
                    order_id=str(order_id),
                    vendor_item_ids=[int(x) for x in vendor_item_ids],
                    receipt_counts=[int(x) for x in receipt_counts],
                    user_id=str(user_id),
                )
                resp = resp if isinstance(resp, dict) else {"_raw": resp}
                data = resp.get("data") if isinstance(resp, dict) else None
                failed_items = data.get("failedItemIds") if isinstance(data, dict) else None
                ok = code < 300 and (not failed_items)
            else:
                break

            session.add(
                SupplierRawFetchLog(
                    supplier_code="coupang",
                    account_id=account.id,
                    endpoint=log.endpoint,
                    request_payload={**request_payload, "retryOf": str(log.id), "attempt": attempt},
                    http_status=code,
                    response_payload=resp if isinstance(resp, dict) else {"_raw": resp},
                    error_message=None if ok else "retry failed",
                )
            )
            session.commit()

            if ok:
                succeeded += 1
                break

            if attempt < attempts:
                time.sleep(min(8, 2 ** (attempt - 1)))

        if not ok:
            failed += 1

    return {"processed": len(logs), "succeeded": succeeded, "failed": failed}
