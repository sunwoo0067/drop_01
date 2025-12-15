import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import SupplierSyncJob
from app.ownerclan_sync import start_background_ownerclan_job
from app.session_factory import session_factory

router = APIRouter()


def _to_iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.isoformat()


class OwnerClanSyncRequestIn(BaseModel):
    params: dict = Field(default_factory=dict)


def _enqueue_job(session: Session, supplier_code: str, job_type: str, params: dict) -> SupplierSyncJob:
    job = SupplierSyncJob(supplier_code=supplier_code, job_type=job_type, status="queued", params=params or {})
    session.add(job)
    session.flush()
    return job


@router.post("/ownerclan/sync/items")
def trigger_ownerclan_items(
    payload: OwnerClanSyncRequestIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    job = _enqueue_job(session, "ownerclan", "ownerclan_items_raw", payload.params)
    background_tasks.add_task(start_background_ownerclan_job, session_factory, uuid.UUID(str(job.id)))
    return {"jobId": str(job.id)}


@router.post("/ownerclan/sync/orders")
def trigger_ownerclan_orders(
    payload: OwnerClanSyncRequestIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    job = _enqueue_job(session, "ownerclan", "ownerclan_orders_raw", payload.params)
    background_tasks.add_task(start_background_ownerclan_job, session_factory, uuid.UUID(str(job.id)))
    return {"jobId": str(job.id)}


@router.post("/ownerclan/sync/qna")
def trigger_ownerclan_qna(
    payload: OwnerClanSyncRequestIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    job = _enqueue_job(session, "ownerclan", "ownerclan_qna_raw", payload.params)
    background_tasks.add_task(start_background_ownerclan_job, session_factory, uuid.UUID(str(job.id)))
    return {"jobId": str(job.id)}


@router.post("/ownerclan/sync/categories")
def trigger_ownerclan_categories(
    payload: OwnerClanSyncRequestIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    job = _enqueue_job(session, "ownerclan", "ownerclan_categories_raw", payload.params)
    background_tasks.add_task(start_background_ownerclan_job, session_factory, uuid.UUID(str(job.id)))
    return {"jobId": str(job.id)}


@router.get("/sync/jobs")
def list_sync_jobs(
    session: Session = Depends(get_session),
    supplier_code: str | None = Query(default=None, alias="supplierCode"),
    limit: int = Query(default=30, ge=1, le=200),
) -> list[dict]:
    stmt = select(SupplierSyncJob).order_by(SupplierSyncJob.created_at.desc()).limit(limit)
    if supplier_code:
        stmt = stmt.where(SupplierSyncJob.supplier_code == supplier_code)

    jobs = session.scalars(stmt).all()

    result: list[dict] = []
    for job in jobs:
        result.append(
            {
                "id": str(job.id),
                "supplierCode": job.supplier_code,
                "jobType": job.job_type,
                "status": job.status,
                "progress": job.progress,
                "lastError": job.last_error,
                "params": job.params,
                "startedAt": _to_iso(job.started_at),
                "finishedAt": _to_iso(job.finished_at),
                "createdAt": _to_iso(job.created_at),
                "updatedAt": _to_iso(job.updated_at),
            }
        )

    return result


@router.get("/sync/jobs/{job_id}")
def get_sync_job(job_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    job = session.get(SupplierSyncJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job을 찾을 수 없습니다")

    return {
        "id": str(job.id),
        "supplierCode": job.supplier_code,
        "jobType": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "lastError": job.last_error,
        "params": job.params,
        "startedAt": _to_iso(job.started_at),
        "finishedAt": _to_iso(job.finished_at),
        "createdAt": _to_iso(job.created_at),
        "updatedAt": _to_iso(job.updated_at),
    }
