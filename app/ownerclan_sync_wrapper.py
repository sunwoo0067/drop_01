"""
OwnerClan 동기화 래퍼.

기존 app/ownerclan_sync.py의 sync_ownerclan_items_raw 함수를 호출하여
새로운 OwnerClanItemSyncHandler 클래스를 사용합니다.
"""

from sqlalchemy.orm import Session
from app.models import SupplierSyncJob
from app.ownerclan_sync import sync_ownerclan_items_raw, OwnerClanJobResult


def sync_ownerclan_items_raw_wrapper(session: Session, job: SupplierSyncJob) -> OwnerClanJobResult:
    """
    OwnerClan 아이템 동기화 (핸들러 버전).
    
    새로운 OwnerClanItemSyncHandler 클래스를 사용하여 유지보수성/테스트 용이성을 확보합니다.
    """
    return sync_ownerclan_items_raw(session, job)
