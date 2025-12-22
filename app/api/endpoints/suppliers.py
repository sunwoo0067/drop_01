import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.db import get_session
from app.models import SupplierAccount, SupplierCategoryRaw, SupplierItemRaw, SupplierOrderRaw, SupplierQnaRaw, SupplierSyncJob
from app.ownerclan_client import OwnerClanClient
from app.settings import settings
from app.ownerclan_sync import start_background_ownerclan_job
from app.session_factory import session_factory
from app.services.detail_html_normalizer import normalize_ownerclan_html

router = APIRouter()


def _to_iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.isoformat()


class OwnerClanSyncRequestIn(BaseModel):
    params: dict = Field(default_factory=dict)


class OwnerClanItemsSearchOut(BaseModel):
    itemCode: str | None = None
    itemName: str | None = None
    supplyPrice: int | None = None
    raw: dict | None = None


class OwnerClanItemImportIn(BaseModel):
    itemCode: str


def _enqueue_job(session: Session, supplier_code: str, job_type: str, params: dict) -> SupplierSyncJob:
    job = SupplierSyncJob(supplier_code=supplier_code, job_type=job_type, status="queued", params=params or {})
    session.add(job)
    session.flush()
    return job


def _cleanup_stale_jobs(
    session: Session,
    supplier_code: str | None,
    max_age_minutes: int = 60,
) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(1, int(max_age_minutes)))

    stmt = select(SupplierSyncJob).where(SupplierSyncJob.status.in_(["queued", "running"]))
    if supplier_code:
        stmt = stmt.where(SupplierSyncJob.supplier_code == supplier_code)
    stmt = stmt.where(SupplierSyncJob.updated_at < cutoff)

    jobs = session.scalars(stmt).all()
    if not jobs:
        return 0

    now = datetime.now(timezone.utc)
    changed = 0
    for job in jobs:
        job.status = "failed"
        if not job.finished_at:
            job.finished_at = now
        if not job.last_error:
            job.last_error = "서버 재시작/중단으로 작업이 종료되지 않아 자동 실패 처리되었습니다(stale job)"
        changed += 1

    session.flush()
    return changed


def _ensure_no_running_job(session: Session, supplier_code: str, job_type: str) -> None:
    existing = (
        session.query(SupplierSyncJob)
        .filter(SupplierSyncJob.supplier_code == supplier_code)
        .filter(SupplierSyncJob.job_type == job_type)
        .filter(SupplierSyncJob.status.in_(["queued", "running"]))
        .order_by(SupplierSyncJob.created_at.desc())
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"이미 실행중인 작업이 있습니다(jobId={existing.id})")


@router.post("/ownerclan/sync/items")
def trigger_ownerclan_items(
    payload: OwnerClanSyncRequestIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    _cleanup_stale_jobs(session, supplier_code="ownerclan")
    _ensure_no_running_job(session, supplier_code="ownerclan", job_type="ownerclan_items_raw")
    job = _enqueue_job(session, "ownerclan", "ownerclan_items_raw", payload.params)
    session.commit()
    background_tasks.add_task(start_background_ownerclan_job, session_factory, uuid.UUID(str(job.id)))
    return {"jobId": str(job.id)}


@router.post("/ownerclan/sync/orders")
def trigger_ownerclan_orders(
    payload: OwnerClanSyncRequestIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    _cleanup_stale_jobs(session, supplier_code="ownerclan")
    _ensure_no_running_job(session, supplier_code="ownerclan", job_type="ownerclan_orders_raw")
    job = _enqueue_job(session, "ownerclan", "ownerclan_orders_raw", payload.params)
    session.commit()
    background_tasks.add_task(start_background_ownerclan_job, session_factory, uuid.UUID(str(job.id)))
    return {"jobId": str(job.id)}


@router.post("/ownerclan/sync/qna")
def trigger_ownerclan_qna(
    payload: OwnerClanSyncRequestIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    _cleanup_stale_jobs(session, supplier_code="ownerclan")
    _ensure_no_running_job(session, supplier_code="ownerclan", job_type="ownerclan_qna_raw")
    job = _enqueue_job(session, "ownerclan", "ownerclan_qna_raw", payload.params)
    session.commit()
    background_tasks.add_task(start_background_ownerclan_job, session_factory, uuid.UUID(str(job.id)))
    return {"jobId": str(job.id)}


@router.post("/ownerclan/sync/categories")
def trigger_ownerclan_categories(
    payload: OwnerClanSyncRequestIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    _cleanup_stale_jobs(session, supplier_code="ownerclan")
    _ensure_no_running_job(session, supplier_code="ownerclan", job_type="ownerclan_categories_raw")
    job = _enqueue_job(session, "ownerclan", "ownerclan_categories_raw", payload.params)
    session.commit()
    background_tasks.add_task(start_background_ownerclan_job, session_factory, uuid.UUID(str(job.id)))
    return {"jobId": str(job.id)}


@router.get("/sync/jobs")
def list_sync_jobs(
    session: Session = Depends(get_session),
    supplier_code: str | None = Query(default=None, alias="supplierCode"),
    limit: int = Query(default=30, ge=1, le=200),
) -> list[dict]:
    _cleanup_stale_jobs(session, supplier_code=supplier_code)
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


@router.get("/ownerclan/items/search")
def search_ownerclan_items(
    session: Session = Depends(get_session),
    keyword: str = Query(..., min_length=1),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict:
    account = (
        session.query(SupplierAccount)
        .filter(SupplierAccount.supplier_code == "ownerclan")
        .filter(SupplierAccount.user_type == "seller")
        .filter(SupplierAccount.is_primary.is_(True))
        .filter(SupplierAccount.is_active.is_(True))
        .one_or_none()
    )
    if not account:
        raise HTTPException(status_code=400, detail="오너클랜(seller) 대표 계정이 설정되어 있지 않습니다")

    client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
        access_token=account.access_token,
    )

    status_code, data = client.get_products(keyword=keyword, page=page, limit=limit)
    if status_code >= 400:
        raise HTTPException(status_code=400, detail=f"오너클랜 상품 검색 실패: HTTP {status_code}")

    data_obj = data.get("data") if isinstance(data, dict) else None
    items_obj = None
    if isinstance(data_obj, dict):
        items_obj = data_obj.get("items")
        if items_obj is None and isinstance(data_obj.get("data"), dict):
            items_obj = data_obj.get("data").get("items")

    items_list = items_obj if isinstance(items_obj, list) else []
    result_items: list[dict] = []
    for it in items_list:
        if not isinstance(it, dict):
            continue
        item_code = it.get("item_code") or it.get("itemCode") or it.get("item_code") or it.get("item")
        item_name = it.get("item_name") or it.get("name") or it.get("itemName")
        supply_price = it.get("supply_price") or it.get("supplyPrice")
        try:
            supply_price_int = int(float(supply_price)) if supply_price is not None else None
        except Exception:
            supply_price_int = None
        result_items.append(
            {
                "itemCode": str(item_code) if item_code is not None else None,
                "itemName": str(item_name) if item_name is not None else None,
                "supplyPrice": supply_price_int,
                "raw": it,
            }
        )

    return {"httpStatus": status_code, "keyword": keyword, "page": page, "limit": limit, "items": result_items}


@router.post("/ownerclan/items/import", status_code=200)
def import_ownerclan_item(payload: OwnerClanItemImportIn, session: Session = Depends(get_session)) -> dict:
    item_code = str(payload.itemCode or "").strip()
    if not item_code:
        raise HTTPException(status_code=400, detail="itemCode가 필요합니다")

    account = (
        session.query(SupplierAccount)
        .filter(SupplierAccount.supplier_code == "ownerclan")
        .filter(SupplierAccount.user_type == "seller")
        .filter(SupplierAccount.is_primary.is_(True))
        .filter(SupplierAccount.is_active.is_(True))
        .one_or_none()
    )
    if not account:
        raise HTTPException(status_code=400, detail="오너클랜(seller) 대표 계정이 설정되어 있지 않습니다")

    client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
        access_token=account.access_token,
    )

    status_code, data = client.get_product(item_code)
    if status_code >= 400:
        raise HTTPException(status_code=400, detail=f"오너클랜 상품 조회 실패(itemCode={item_code}): HTTP {status_code}")

    data_obj = data.get("data") if isinstance(data, dict) else None
    if not isinstance(data_obj, dict):
        data_obj = {}

    source_updated_at = data_obj.get("updatedAt") or data_obj.get("updated_at")
    detail_html = data_obj.get("detail_html") or data_obj.get("detailHtml")
    if isinstance(detail_html, str) and detail_html.strip():
        data_obj = {**data_obj, "detail_html": normalize_ownerclan_html(detail_html)}
    else:
        content = data_obj.get("content") or data_obj.get("description")
        if isinstance(content, str) and content.strip():
            data_obj = {**data_obj, "detail_html": normalize_ownerclan_html(content)}

    stmt = insert(SupplierItemRaw).values(
        supplier_code="ownerclan",
        item_code=item_code,
        item_key=str(data_obj.get("key")) if data_obj.get("key") is not None else None,
        item_id=str(data_obj.get("id")) if data_obj.get("id") is not None else None,
        source_updated_at=source_updated_at,
        raw=data_obj,
        fetched_at=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["supplier_code", "item_code"],
        set_={
            "item_key": stmt.excluded.item_key,
            "item_id": stmt.excluded.item_id,
            "raw": stmt.excluded.raw,
            "fetched_at": stmt.excluded.fetched_at,
        },
    )
    session.execute(stmt)

    row = (
        session.query(SupplierItemRaw)
        .filter(SupplierItemRaw.supplier_code == "ownerclan")
        .filter(SupplierItemRaw.item_code == item_code)
        .one_or_none()
    )

    return {"imported": True, "itemCode": item_code, "supplierItemRawId": str(row.id) if row else None}


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
        stmt = stmt.where(
            or_(
                SupplierItemRaw.item_code.ilike(like),
                SupplierItemRaw.item_key.ilike(like),
                SupplierItemRaw.raw["item_name"].astext.ilike(like),
                SupplierItemRaw.raw["name"].astext.ilike(like),
            )
        )

    items = session.scalars(stmt).all()

    result: list[dict] = []
    for item in items:
        raw = item.raw if isinstance(item.raw, dict) else {}
        item_name = raw.get("item_name") or raw.get("name")

        supply_price = raw.get("supply_price") or raw.get("supplyPrice") or raw.get("fixedPrice") or raw.get("price")
        try:
            supply_price_int = int(float(supply_price)) if supply_price is not None else None
        except Exception:
            supply_price_int = None
        result.append(
            {
                "id": str(item.id),
                "supplierCode": item.supplier_code,
                "itemCode": item.item_code,
                "itemKey": item.item_key,
                "itemId": item.item_id,
                "itemName": item_name,
                "supplyPrice": supply_price_int,
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
@router.post("/ownerclan/import-raw")
def trigger_import_raw_to_candidate(
    limit: int = Query(1000, description="Max items to import"),
    session: Session = Depends(get_session),
) -> dict:
    """
    Manually triggers conversion of SupplierItemRaw to SourcingCandidate.
    Useful for testing or recovering missed items.
    """
    from app.services.sourcing_service import SourcingService
    service = SourcingService(session)
    count = service.import_from_raw(limit=limit)
    return {"status": "success", "imported_count": count}
