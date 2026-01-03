from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session
from app.models import SupplierSyncJob
from app.services.ownerclan.core import OwnerClanJobResult
from app.services.ownerclan.dispatcher import run_ownerclan_job as _run_ownerclan_job
from app.services.ownerclan.jobs import start_background_ownerclan_job as _start_background_ownerclan_job
from app.services.ownerclan.sync import (
    sync_ownerclan_orders_raw as _sync_ownerclan_orders_raw,
    sync_ownerclan_qna_raw as _sync_ownerclan_qna_raw,
    sync_ownerclan_categories_raw as _sync_ownerclan_categories_raw,
    sync_ownerclan_items_raw as _sync_ownerclan_items_raw,
)

logger = logging.getLogger(__name__)

# --- Redirection Layer for Backward Compatibility ---

def run_ownerclan_job(session: Session, job: SupplierSyncJob) -> OwnerClanJobResult:
    """Redirects to dispatcher."""
    return _run_ownerclan_job(session, job)

def start_background_ownerclan_job(session_factory: Any, job_id: uuid.UUID) -> None:
    """Redirects to jobs."""
    _start_background_ownerclan_job(session_factory, job_id)

def sync_ownerclan_orders_raw(session: Session, job: SupplierSyncJob) -> OwnerClanJobResult:
    return _sync_ownerclan_orders_raw(session, job)

def sync_ownerclan_qna_raw(session: Session, job: SupplierSyncJob) -> OwnerClanJobResult:
    return _sync_ownerclan_qna_raw(session, job)

def sync_ownerclan_categories_raw(session: Session, job: SupplierSyncJob) -> OwnerClanJobResult:
    return _sync_ownerclan_categories_raw(session, job)

def sync_ownerclan_items_raw(session: Session, job: SupplierSyncJob) -> OwnerClanJobResult:
    return _sync_ownerclan_items_raw(session, job)
