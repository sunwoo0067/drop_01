import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import SupplierCategoryRaw, SupplierItemRaw, SupplierOrderRaw, SupplierQnaRaw, SupplierSyncJob
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


@router.get("/ownerclan/raw/items")
def list_ownerclan_items_raw(
    session: Session = Depends(get_session),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    stmt = (
        select(SupplierItemRaw)
        .where(SupplierItemRaw.supplier_code == "ownerclan")
        .order_by(SupplierItemRaw.fetched_at.desc())
        .offset(offset)
        .limit(limit)
    )

    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(SupplierItemRaw.item_code.ilike(like), SupplierItemRaw.item_key.ilike(like)))

    items = session.scalars(stmt).all()

    result: list[dict] = []
    for item in items:
        result.append(
            {
                "id": str(item.id),
                "supplierCode": item.supplier_code,
                "itemCode": item.item_code,
                "itemKey": item.item_key,
                "itemId": item.item_id,
                "sourceUpdatedAt": _to_iso(item.source_updated_at),
                "fetchedAt": _to_iso(item.fetched_at),
            }
        )

    return result


@router.get("/ownerclan/raw/items/{item_raw_id}")
def get_ownerclan_item_raw(item_raw_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    item = session.get(SupplierItemRaw, item_raw_id)
    if not item or item.supplier_code != "ownerclan":
        raise HTTPException(status_code=404, detail="raw item을 찾을 수 없습니다")

    return {
        "id": str(item.id),
        "supplierCode": item.supplier_code,
        "itemCode": item.item_code,
        "itemKey": item.item_key,
        "itemId": item.item_id,
        "sourceUpdatedAt": _to_iso(item.source_updated_at),
        "fetchedAt": _to_iso(item.fetched_at),
        "raw": item.raw,
    }


@router.get("/ownerclan/raw/orders")
def list_ownerclan_orders_raw(
    session: Session = Depends(get_session),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    stmt = (
        select(SupplierOrderRaw)
        .where(SupplierOrderRaw.supplier_code == "ownerclan")
        .order_by(SupplierOrderRaw.fetched_at.desc())
        .offset(offset)
        .limit(limit)
    )

    if q:
        like = f"%{q}%"
        stmt = stmt.where(SupplierOrderRaw.order_id.ilike(like))

    orders = session.scalars(stmt).all()

    result: list[dict] = []
    for order in orders:
        result.append(
            {
                "id": str(order.id),
                "supplierCode": order.supplier_code,
                "accountId": str(order.account_id),
                "orderId": order.order_id,
                "fetchedAt": _to_iso(order.fetched_at),
            }
        )

    return result


@router.get("/ownerclan/raw/orders/{order_raw_id}")
def get_ownerclan_order_raw(order_raw_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    order = session.get(SupplierOrderRaw, order_raw_id)
    if not order or order.supplier_code != "ownerclan":
        raise HTTPException(status_code=404, detail="raw order를 찾을 수 없습니다")

    return {
        "id": str(order.id),
        "supplierCode": order.supplier_code,
        "accountId": str(order.account_id),
        "orderId": order.order_id,
        "fetchedAt": _to_iso(order.fetched_at),
        "raw": order.raw,
    }


@router.get("/ownerclan/raw/qna")
def list_ownerclan_qna_raw(
    session: Session = Depends(get_session),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    stmt = (
        select(SupplierQnaRaw)
        .where(SupplierQnaRaw.supplier_code == "ownerclan")
        .order_by(SupplierQnaRaw.fetched_at.desc())
        .offset(offset)
        .limit(limit)
    )

    if q:
        like = f"%{q}%"
        stmt = stmt.where(SupplierQnaRaw.qna_id.ilike(like))

    qna_rows = session.scalars(stmt).all()

    result: list[dict] = []
    for qna in qna_rows:
        result.append(
            {
                "id": str(qna.id),
                "supplierCode": qna.supplier_code,
                "accountId": str(qna.account_id),
                "qnaId": qna.qna_id,
                "fetchedAt": _to_iso(qna.fetched_at),
            }
        )

    return result


@router.get("/ownerclan/raw/qna/{qna_raw_id}")
def get_ownerclan_qna_raw(qna_raw_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    qna = session.get(SupplierQnaRaw, qna_raw_id)
    if not qna or qna.supplier_code != "ownerclan":
        raise HTTPException(status_code=404, detail="raw qna를 찾을 수 없습니다")

    return {
        "id": str(qna.id),
        "supplierCode": qna.supplier_code,
        "accountId": str(qna.account_id),
        "qnaId": qna.qna_id,
        "fetchedAt": _to_iso(qna.fetched_at),
        "raw": qna.raw,
    }


@router.get("/ownerclan/raw/categories")
def list_ownerclan_categories_raw(
    session: Session = Depends(get_session),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    stmt = (
        select(SupplierCategoryRaw)
        .where(SupplierCategoryRaw.supplier_code == "ownerclan")
        .order_by(SupplierCategoryRaw.fetched_at.desc())
        .offset(offset)
        .limit(limit)
    )

    if q:
        like = f"%{q}%"
        stmt = stmt.where(SupplierCategoryRaw.category_id.ilike(like))

    categories = session.scalars(stmt).all()

    result: list[dict] = []
    for category in categories:
        result.append(
            {
                "id": str(category.id),
                "supplierCode": category.supplier_code,
                "categoryId": category.category_id,
                "fetchedAt": _to_iso(category.fetched_at),
            }
        )

    return result


@router.get("/ownerclan/raw/categories/{category_raw_id}")
def get_ownerclan_category_raw(category_raw_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    category = session.get(SupplierCategoryRaw, category_raw_id)
    if not category or category.supplier_code != "ownerclan":
        raise HTTPException(status_code=404, detail="raw category를 찾을 수 없습니다")

    return {
        "id": str(category.id),
        "supplierCode": category.supplier_code,
        "categoryId": category.category_id,
        "fetchedAt": _to_iso(category.fetched_at),
        "raw": category.raw,
    }
