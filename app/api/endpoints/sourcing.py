from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from typing import List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
import logging
import uuid
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db import get_session
from app.services.sourcing_service import SourcingService
from app.models import SourcingCandidate, SupplierAccount, SupplierItemRaw, Product, MarketAccount
from app.ownerclan_client import OwnerClanClient
from app.settings import settings

router = APIRouter()

logger = logging.getLogger(__name__)

class KeywordSourceIn(BaseModel):
    keywords: List[str]
    min_margin: float = 0.15


class SourcingCandidateUpdateIn(BaseModel):
    status: str


class PromoteCandidateIn(BaseModel):
    autoProcess: bool = False
    autoRegisterCoupang: bool = False
    forceFetchOwnerClan: bool = False
    minImagesRequired: int = Field(default=3, ge=1, le=20)


def _parse_int_price(value) -> int:
    if value is None:
        return 0
    try:
        return int(float(value))
    except Exception:
        return 0


def _normalize_ownerclan_item_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


def _get_or_fetch_supplier_item_raw(
    session: Session,
    item_code: str,
    force_fetch: bool,
) -> SupplierItemRaw | None:
    item_code_norm = str(item_code or "").strip()
    if not item_code_norm:
        return None

    raw_item = (
        session.execute(
            select(SupplierItemRaw)
            .where(SupplierItemRaw.supplier_code == "ownerclan")
            .where(SupplierItemRaw.item_code == item_code_norm)
        )
        .scalars()
        .first()
    )
    if raw_item and not force_fetch:
        return raw_item

    owner = (
        session.query(SupplierAccount)
        .filter(SupplierAccount.supplier_code == "ownerclan")
        .filter(SupplierAccount.user_type == "seller")
        .filter(SupplierAccount.is_primary.is_(True))
        .filter(SupplierAccount.is_active.is_(True))
        .one_or_none()
    )
    if not owner or not owner.access_token:
        raise HTTPException(status_code=400, detail="오너클랜(seller) 대표 계정이 설정되어 있지 않습니다")

    client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
        access_token=owner.access_token,
    )
    status_code, data = client.get_product(item_code_norm)
    if status_code >= 400:
        raise HTTPException(status_code=400, detail=f"오너클랜 상품 조회 실패: HTTP {status_code}")

    raw_payload = _normalize_ownerclan_item_payload(data)
    now = datetime.now(timezone.utc)
    stmt = insert(SupplierItemRaw).values(
        supplier_code="ownerclan",
        item_code=item_code_norm,
        item_key=str(raw_payload.get("key")) if raw_payload.get("key") is not None else None,
        item_id=str(raw_payload.get("id")) if raw_payload.get("id") is not None else None,
        fetched_at=now,
        raw=raw_payload,
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
    session.flush()

    raw_item = (
        session.execute(
            select(SupplierItemRaw)
            .where(SupplierItemRaw.supplier_code == "ownerclan")
            .where(SupplierItemRaw.item_code == item_code_norm)
        )
        .scalars()
        .first()
    )
    return raw_item


def _create_or_get_product_from_raw_item(session: Session, raw_item: SupplierItemRaw) -> tuple[Product, bool]:
    existing = (
        session.execute(select(Product).where(Product.supplier_item_id == raw_item.id)).scalars().first()
    )
    if existing:
        return existing, False

    data = raw_item.raw if isinstance(raw_item.raw, dict) else {}
    item_name = data.get("item_name") or data.get("name") or data.get("itemName") or "Untitled"
    supply_price = (
        data.get("supply_price")
        or data.get("supplyPrice")
        or data.get("fixedPrice")
        or data.get("fixed_price")
        or data.get("price")
        or 0
    )
    brand_name = data.get("brand") or data.get("brand_name")
    description = data.get("description") or data.get("content")

    cost = _parse_int_price(supply_price)
    try:
        margin_rate = float(settings.pricing_default_margin_rate or 0.0)
    except Exception:
        margin_rate = 0.0
    if margin_rate < 0:
        margin_rate = 0.0
    selling_price = int(cost * (1.0 + margin_rate))

    product = Product(
        supplier_item_id=raw_item.id,
        name=str(item_name),
        brand=str(brand_name) if brand_name is not None else None,
        description=str(description) if description is not None else None,
        cost_price=cost,
        selling_price=selling_price,
        status="DRAFT",
    )
    session.add(product)
    session.flush()
    return product, True


async def _execute_post_promote_actions(product_id: uuid.UUID, auto_register_coupang: bool, min_images_required: int) -> None:
    from app.session_factory import session_factory
    from app.services.processing_service import ProcessingService
    from app.coupang_sync import register_product

    with session_factory() as bg_session:
        service = ProcessingService(bg_session)
        effective_min_images_required = int(min_images_required)
        if auto_register_coupang:
            effective_min_images_required = 5
        await service.process_product(product_id, min_images_required=effective_min_images_required)

        if not auto_register_coupang:
            return

        product = bg_session.get(Product, product_id)
        if not product:
            return

        if product.status != "DRAFT" or product.processing_status != "COMPLETED":
            return

        account = (
            bg_session.execute(
                select(MarketAccount)
                .where(MarketAccount.market_code == "COUPANG")
                .where(MarketAccount.is_active == True)
            )
            .scalars()
            .first()
        )
        if not account:
            return

        ok, _reason = register_product(bg_session, account.id, product.id)
        if ok:
            product.status = "ACTIVE"
            bg_session.commit()


def _execute_post_promote_actions_bg(product_id: uuid.UUID, auto_register_coupang: bool, min_images_required: int) -> None:
    import asyncio

    asyncio.run(
        _execute_post_promote_actions(
            product_id,
            bool(auto_register_coupang),
            int(min_images_required),
        )
    )

@router.get("/candidates")
def list_sourcing_candidates(
    session: Session = Depends(get_session),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    strategy: str | None = Query(default=None),
    supplier_code: str | None = Query(default=None, alias="supplierCode"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    stmt = select(SourcingCandidate).order_by(SourcingCandidate.created_at.desc()).offset(offset).limit(limit)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(SourcingCandidate.name.ilike(like))
    if status:
        stmt = stmt.where(SourcingCandidate.status == status)
    if strategy:
        stmt = stmt.where(SourcingCandidate.source_strategy == strategy)
    if supplier_code:
        stmt = stmt.where(SourcingCandidate.supplier_code == supplier_code)

    rows = session.scalars(stmt).all()
    result: list[dict] = []
    for row in rows:
        result.append(
            {
                "id": str(row.id),
                "supplierCode": row.supplier_code,
                "supplierItemId": row.supplier_item_id,
                "name": row.name,
                "supplyPrice": row.supply_price,
                "sourceStrategy": row.source_strategy,
                "benchmarkProductId": str(row.benchmark_product_id) if row.benchmark_product_id else None,
                "similarityScore": row.similarity_score,
                "seasonalScore": row.seasonal_score,
                "marginScore": row.margin_score,
                "finalScore": row.final_score,
                "specData": row.spec_data,
                "seoKeywords": row.seo_keywords,
                "targetEvent": row.target_event,
                "thumbnailUrl": row.thumbnail_url,
                "status": row.status,
                "createdAt": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return result

@router.get("/candidates/{candidate_id}")
def get_sourcing_candidate(candidate_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    row = session.get(SourcingCandidate, candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="소싱 후보를 찾을 수 없습니다")

    return {
        "id": str(row.id),
        "supplierCode": row.supplier_code,
        "supplierItemId": row.supplier_item_id,
        "name": row.name,
        "supplyPrice": row.supply_price,
        "sourceStrategy": row.source_strategy,
        "benchmarkProductId": str(row.benchmark_product_id) if row.benchmark_product_id else None,
        "similarityScore": row.similarity_score,
        "seasonalScore": row.seasonal_score,
        "marginScore": row.margin_score,
        "finalScore": row.final_score,
        "specData": row.spec_data,
        "seoKeywords": row.seo_keywords,
        "targetEvent": row.target_event,
        "thumbnailUrl": row.thumbnail_url,
        "status": row.status,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
    }

@router.post("/keyword")
async def trigger_keyword_sourcing(
    payload: KeywordSourceIn,
    background_tasks: BackgroundTasks,
):
    """
    Triggers sourcing based on a list of keywords.
    Runs in a dedicated background thread to minimize operational risk.
    """
    background_tasks.add_task(_execute_global_keyword_sourcing, payload.keywords, float(payload.min_margin))
    
    return {"status": "accepted", "message": f"Global keyword sourcing started for {len(payload.keywords)} keywords"}

def _execute_global_keyword_sourcing(keywords: list[str], min_margin: float) -> None:
    import traceback
    from app.session_factory import session_factory
    from app.services.sourcing_service import SourcingService

    try:
        with session_factory() as session:
            service = SourcingService(session)
            service.execute_keyword_sourcing(keywords, float(min_margin))
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Error in global keyword sourcing:\n{error_trace}")

async def _execute_benchmark_sourcing(benchmark_id: uuid.UUID, job_id: uuid.UUID) -> None:
    import traceback
    from app.session_factory import session_factory
    from app.services.sourcing_service import SourcingService
    from app.models import SupplierSyncJob
    from datetime import datetime, timezone

    # 1. Start Job
    with session_factory() as session:
        job = session.get(SupplierSyncJob, job_id)
        if job:
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            session.commit()

    try:
        # 2. Execute Sourcing
        logger.info(f"Starting long-running sourcing job {job_id} for benchmark {benchmark_id}")
        with session_factory() as session:
            service = SourcingService(session)
            await service.execute_benchmark_sourcing(benchmark_id)
            
        # 3. Success
        with session_factory() as session:
            job = session.get(SupplierSyncJob, job_id)
            if job:
                job.status = "succeeded"
                job.finished_at = datetime.now(timezone.utc)
                job.progress = 100
                session.commit()
        logger.info(f"Successfully completed sourcing job {job_id}")

    except Exception as e:
        # 4. Failure - 전체 Traceback 기록
        error_trace = traceback.format_exc()
        logger.error(f"Error in sourcing job {job_id} (benchmark: {benchmark_id}):\n{error_trace}")
        
        with session_factory() as session:
            job = session.get(SupplierSyncJob, job_id)
            if job:
                job.status = "failed"
                # 상세 컨텍스트를 포함한 에러 메시지 저장
                job.last_error = f"Benchmark[{benchmark_id}]: {str(e)}\n\n{error_trace}"
                job.finished_at = datetime.now(timezone.utc)
                session.commit()
        # 이미 로깅 및 상태 기록을 완료했으므로 상위로 전파하지 않거나, 필요 시 로깅 후 조용히 종료 가능
        # 여기서는 백그라운드 스레드이므로 raise 해도 앱 전체에 영향 없음


@router.post("/benchmark/{benchmark_id}")
async def trigger_benchmark_sourcing(
    benchmark_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """
    Triggers smart sourcing based on a Benchmark Product (Gap Analysis, Spec Matching).
    Runs in a dedicated background thread with SupplierSyncJob tracking to minimize operational risk.
    """
    from app.models import SupplierSyncJob
    
    # 1. Create Job Entry
    job = SupplierSyncJob(
        id=uuid.uuid4(),
        supplier_code="ownerclan",
        job_type="benchmark_sourcing",
        status="queued",
        params={"benchmark_id": str(benchmark_id)},
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    background_tasks.add_task(_execute_benchmark_sourcing_bg, benchmark_id, job.id)
    
    return {
        "status": "accepted", 
        "message": f"Benchmark sourcing started for {benchmark_id}",
        "jobId": str(job.id)
    }


def _execute_benchmark_sourcing_bg(benchmark_id: uuid.UUID, job_id: uuid.UUID) -> None:
    import asyncio

    asyncio.run(_execute_benchmark_sourcing(benchmark_id, job_id))


@router.patch("/candidates/{candidate_id}")
def update_sourcing_candidate(
    candidate_id: uuid.UUID,
    payload: SourcingCandidateUpdateIn,
    session: Session = Depends(get_session),
) -> dict:
    candidate = session.get(SourcingCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="소싱 후보를 찾을 수 없습니다")

    new_status = str(payload.status or "").strip().upper()
    if new_status not in ("PENDING", "APPROVED", "REJECTED"):
        raise HTTPException(status_code=400, detail="status는 PENDING/APPROVED/REJECTED 중 하나여야 합니다")

    candidate.status = new_status
    session.flush()

    return {
        "updated": True,
        "candidate": {
            "id": str(candidate.id),
            "status": candidate.status,
        },
    }


@router.post("/candidates/{candidate_id}/promote", status_code=200)
def promote_sourcing_candidate(
    candidate_id: uuid.UUID,
    payload: PromoteCandidateIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    candidate = session.get(SourcingCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="소싱 후보를 찾을 수 없습니다")

    if str(candidate.supplier_code or "").strip().lower() != "ownerclan":
        raise HTTPException(status_code=400, detail="현재는 ownerclan 후보만 승격할 수 있습니다")

    if str(candidate.status or "").strip().upper() != "APPROVED":
        raise HTTPException(status_code=409, detail="APPROVED 상태의 후보만 승격할 수 있습니다")

    raw_item = _get_or_fetch_supplier_item_raw(
        session,
        item_code=str(candidate.supplier_item_id or ""),
        force_fetch=bool(payload.forceFetchOwnerClan),
    )
    if not raw_item:
        raise HTTPException(status_code=404, detail="오너클랜 raw item을 찾을 수 없습니다")

    product, created = _create_or_get_product_from_raw_item(session, raw_item)

    effective_auto_process = bool(payload.autoProcess) or bool(payload.autoRegisterCoupang)

    if effective_auto_process:
        background_tasks.add_task(
            _execute_post_promote_actions_bg,
            product.id,
            bool(payload.autoRegisterCoupang),
            int(payload.minImagesRequired),
        )

    return {
        "created": bool(created),
        "productId": str(product.id),
        "autoProcess": bool(effective_auto_process),
        "autoRegisterCoupang": bool(payload.autoRegisterCoupang),
    }
