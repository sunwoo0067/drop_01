from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session
from app.models import SupplierAccount, SupplierSyncState

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class OwnerClanJobResult:
    """오너클랜 동기화 작업 결과."""
    processed: int
    error: Optional[str] = None

def _parse_ownerclan_datetime(value: Any) -> datetime | None:
    """오너클랜 날짜 형식(ISO8601 or ms) 파싱."""
    if not value:
        return None
    try:
        # 1. 밀리세컨드 타임스탬프 (int/str)
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            ts = int(value) / 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        
        # 2. ISO 8601 문자열
        if isinstance(value, str):
            # Z 또는 +09:00 등을 처리하기 위해 replace 활용 (간단화)
            dt_str = value.replace("Z", "+00:00")
            return datetime.fromisoformat(dt_str)
    except Exception as e:
        logger.warning(f"날짜 파싱 실패 ({value}): {e}")
    return None

def _sanitize_json(value: Any) -> Any:
    """JSON 저장 전 불필요하게 큰 필드나 민감 정보 제거 (상세 정보용)"""
    if isinstance(value, dict):
        new_dict = value.copy()
        # 로깅이나 RAW 저장 시 너무 큰 HTML은 제외할지 결정 가능 (현재는 유지)
        return new_dict
    return value

def get_primary_ownerclan_account(session: Session, user_type: str | None = "seller") -> SupplierAccount | None:
    """DB에서 오너클랜 계정 정보를 조회합니다."""
    base = (
        session.query(SupplierAccount)
        .filter(SupplierAccount.supplier_code == "ownerclan")
        .filter(SupplierAccount.is_active.is_(True))
    )
    if user_type:
        base = base.filter(SupplierAccount.user_type == user_type)

    primary = (
        base.filter(SupplierAccount.is_primary.is_(True))
        .order_by(SupplierAccount.updated_at.desc())
        .first()
    )
    if primary:
        return primary

    return base.order_by(SupplierAccount.updated_at.desc()).first()

def _get_ownerclan_access_token(session: Session, user_type: str = "seller") -> tuple[str | None, str | None]:
    """DB 계정 정보에서 (account_id, access_token)을 가져옵니다."""
    account = get_primary_ownerclan_account(session, user_type)
    if not account:
        return None, None
    token = (account.credentials or {}).get("access_token") or account.access_token
    return str(account.id), token

def upsert_sync_state(session: Session, sync_type: str, watermark_ms: int | None, cursor: str | None):
    """동기화 상태(워터마크, 커서)를 DB에 저장합니다."""
    state = (
        session.query(SupplierSyncState)
        .filter(SupplierSyncState.supplier_code == "ownerclan")
        .filter(SupplierSyncState.sync_type == sync_type)
        .first()
    )
    if not state:
        state = SupplierSyncState(
            supplier_code="ownerclan",
            sync_type=sync_type
        )
        session.add(state)
    
    if watermark_ms is not None:
        state.last_watermark = datetime.fromtimestamp(watermark_ms / 1000.0, tz=timezone.utc)
    if cursor is not None:
        state.last_cursor = cursor
    
    state.updated_at = datetime.now(timezone.utc)
    session.commit()

def get_sync_state(session: Session, sync_type: str) -> SupplierSyncState | None:
    """저장된 동기화 상태를 조회합니다."""
    return (
        session.query(SupplierSyncState)
        .filter(SupplierSyncState.supplier_code == "ownerclan")
        .filter(SupplierSyncState.sync_type == sync_type)
        .first()
    )
