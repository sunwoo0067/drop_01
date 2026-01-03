from __future__ import annotations

import logging
from sqlalchemy.orm import Session

from app.models import SupplierSyncJob
from app.ownerclan_client import OwnerClanClient
from app.settings import settings
from app.ownerclan_sync_handler import OwnerClanItemSyncHandler
from app.services.ownerclan.core import (
    OwnerClanJobResult,
    _get_ownerclan_access_token,
)
# Legacy sync functions
from app.services.ownerclan.sync import (
    sync_ownerclan_items_raw,
    sync_ownerclan_orders_raw,
    sync_ownerclan_qna_raw,
    sync_ownerclan_categories_raw,
)

logger = logging.getLogger(__name__)

def run_ownerclan_job(session: Session, job: SupplierSyncJob) -> OwnerClanJobResult:
    """
    OwnerClan 동기화 작업 디스패처.
    
    Bridge 패턴 적용: "useHandler" 파라미터가 True이면 OwnerClanItemSyncHandler를 사용하고,
    아니면 기존 로직을 그대로 실행하여 하위 호환 보장.
    """
    params = dict(job.params or {})
    use_handler = bool(params.get("useHandler", settings.ownerclan_use_handler))
    
    if job.job_type == "ownerclan_items_raw":
        if use_handler:
            # 신규 핸들러 사용
            _, access_token = _get_ownerclan_access_token(session, user_type="seller")
            client = OwnerClanClient(
                auth_url=settings.ownerclan_auth_url,
                api_base_url=settings.ownerclan_api_base_url,
                graphql_url=settings.ownerclan_graphql_url,
                access_token=access_token,
            )
            
            handler = OwnerClanItemSyncHandler(
                session=session,
                job=job,
                client=client
            )
            
            result = handler.sync()
            if isinstance(result, OwnerClanJobResult):
                return result
            return OwnerClanJobResult(processed=int(result))
        else:
            # Legacy 경로
            return sync_ownerclan_items_raw(session, job)
            
    if job.job_type == "ownerclan_orders_raw":
        return sync_ownerclan_orders_raw(session, job)
        
    if job.job_type == "ownerclan_qna_raw":
        return sync_ownerclan_qna_raw(session, job)
        
    if job.job_type == "ownerclan_categories_raw":
        return sync_ownerclan_categories_raw(session, job)
        
    raise ValueError(f"지원하지 않는 작업 유형입니다: {job.job_type}")
