from __future__ import annotations

import logging
import uuid
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
from app.models import MarketAccount, SupplierRawFetchLog, MarketListing
from app.db import SessionLocal
from app.coupang_client import CoupangClient

logger = logging.getLogger(__name__)

def get_client_for_account(account: MarketAccount) -> CoupangClient:
    """
    MarketAccount 정보를 기반으로 CoupangClient를 초기화합니다.
    """
    if not isinstance(account.credentials, dict):
        raise ValueError(f"Account {account.name} lacks valid credentials")
    
    return CoupangClient(
        vendor_id=account.credentials.get("vendor_id"),
        access_key=account.credentials.get("access_key"),
        secret_key=account.credentials.get("secret_key"),
        vendor_user_id=account.credentials.get("vendor_user_id"),
    )

def log_fetch(session: Session, account: MarketAccount, endpoint: str, payload: dict, code: int, data: dict):
    """
    API 통신 결과를 SupplierRawFetchLog 테이블에 기록합니다.
    """
    def _mask_value(value: object) -> str:
        s = str(value or "")
        if len(s) <= 2:
            return "*" * len(s)
        return f"{'*' * (len(s) - 2)}{s[-2:]}"

    def _sanitize_payload(value: object) -> object:
        if isinstance(value, dict):
            out: dict[str, object] = {}
            for k, v in value.items():
                key = str(k)
                if key in {"vendorId", "vendorUserId"}:
                    out[key] = _mask_value(v)
                    continue
                if key == "content" and isinstance(v, str) and len(v) > 2000:
                    out[key] = v[:2000] + "..."
                    continue
                out[key] = _sanitize_payload(v)
            return out
        if isinstance(value, list):
            return [_sanitize_payload(v) for v in value]
        return value

    safe_payload = payload if isinstance(payload, dict) else {"_raw": payload}
    if endpoint in {"create_product", "update_product_after_create(contents)"}:
        safe_payload = _sanitize_payload(safe_payload)
        
    try:
        with SessionLocal() as log_session:
            log = SupplierRawFetchLog(
                supplier_code="COUPANG",
                account_id=account.id,
                endpoint=endpoint,
                request_payload=safe_payload,
                http_status=code,
                response_payload=data if isinstance(data, dict) else {"_raw": data},
                error_message=data.get("message") if isinstance(data, dict) else None,
                fetched_at=datetime.now(timezone.utc)
            )
            log_session.add(log)
            log_session.commit()
    except Exception as e:
        logger.warning(f"API 로그 기록 실패: {e}")

def log_registration_skip(
    session: Session,
    account: MarketAccount,
    product_id: uuid.UUID,
    reason: str,
    category_code: int | None = None,
) -> None:
    payload = {
        "productId": str(product_id),
        "reason": reason,
    }
    if category_code is not None:
        payload["categoryCode"] = int(category_code)
        
    log_fetch(session, account, "register_product_skipped", payload, 0, {"code": "SKIPPED", "message": reason})

    try:
        with SessionLocal() as log_session:
            listing = (
                log_session.query(MarketListing)
                .filter(MarketListing.market_account_id == account.id)
                .filter(MarketListing.product_id == product_id)
                .first()
            )
            if listing:
                listing.rejection_reason = {
                    "message": reason,
                    "context": "registration_skip",
                }
                log_session.commit()
    except Exception as e:
        logger.warning(f"스킵 사유 저장 실패: {e}")

def name_only_processing() -> bool:
    from app.settings import settings
    return settings.product_processing_name_only
