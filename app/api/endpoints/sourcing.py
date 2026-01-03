from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
import anyio
from pydantic import BaseModel, Field
from typing import List
from sqlalchemy.orm import Session
import logging
import uuid
from sqlalchemy import select

from app.db import get_session
from app.services.sourcing_service import SourcingService
from app.models import SourcingCandidate, Product, MarketAccount
from app.services.ownerclan_items import (
    OwnerClanItemError,
    create_or_get_product_from_raw_item,
    get_or_fetch_ownerclan_item_raw,
)

router = APIRouter()

logger = logging.getLogger(__name__)

class KeywordSourceIn(BaseModel):
    keywords: List[str]
    min_margin: float = 0.15


class KeywordEvaluateIn(BaseModel):
    keyword: str


class KeywordEvaluateOut(BaseModel):
    keyword: str
    grade: str
    score: int
    reason: str
    involved_categories: List[str]


class SourcingCandidateUpdateIn(BaseModel):
    status: str


class PromoteCandidateIn(BaseModel):
    autoProcess: bool = False
    autoRegisterCoupang: bool = False
    forceFetchOwnerClan: bool = False
    minImagesRequired: int = Field(default=1, ge=1, le=20)





async def _execute_post_promote_actions(product_id: uuid.UUID, auto_register_coupang: bool, min_images_required: int) -> None:
    from app.session_factory import session_factory
    from app.services.processing_service import ProcessingService
    from app.services.market_service import MarketService
    from app.services.market_targeting import decide_target_market_for_product

    with session_factory() as bg_session:
        service = ProcessingService(bg_session)
        effective_min_images_required = max(1, int(min_images_required))
        # process_product는 비동기이므로 await로 실행
        await service.process_product(product_id, effective_min_images_required)

        if not auto_register_coupang:
            return

        product = bg_session.get(Product, product_id)
        if not product:
            return

        if product.status != "DRAFT" or product.processing_status != "COMPLETED":
            return

        target_market, _reason = decide_target_market_for_product(bg_session, product)
        m_service = MarketService(bg_session)

        def _get_account(code: str):
            return (
                bg_session.execute(
                    select(MarketAccount)
                    .where(MarketAccount.market_code == code)
                    .where(MarketAccount.is_active == True)
                )
                .scalars()
                .first()
            )

        account = _get_account(target_market)
        if not account and target_market == "COUPANG":
            account = _get_account("SMARTSTORE")
            target_market = "SMARTSTORE"
        if not account:
            return

        result = m_service.register_product(target_market, account.id, product.id)
        if result.get("status") == "success":
            product.status = "ACTIVE"
            bg_session.commit()


async def _execute_post_promote_actions_bg(product_id: uuid.UUID, auto_register_coupang: bool, min_images_required: int) -> None:
    # 1. Promote 후속 조치(이미지 처리, 등록 등)는 동기 I/O가 많으므로 별도 스레드에서 실행
    await anyio.to_thread.run_sync(
        _execute_post_promote_actions_sync_wrapper,
        product_id,
        auto_register_coupang,
        min_images_required
    )

def _execute_post_promote_actions_sync_wrapper(product_id: uuid.UUID, auto_register_coupang: bool, min_images_required: int) -> None:
    # anyio.run을 사용하여 동기 컨텍스트 내에서 비동기 핸들러 실행 (스레드 세이프)
    anyio.run(
        _execute_post_promote_actions,
        product_id,
        auto_register_coupang,
        min_images_required
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
                "thumbnailUrl": row.thumbnail_url,
                "sourceStrategy": row.source_strategy,
                "benchmarkProductId": str(row.benchmark_product_id) if row.benchmark_product_id else None,
                "similarityScore": row.similarity_score,
                "seasonalScore": row.seasonal_score,
                "marginScore": row.margin_score,
                "finalScore": row.final_score,
                "specData": row.spec_data,
                "seoKeywords": row.seo_keywords,
                "targetEvent": row.target_event,
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
        "thumbnailUrl": row.thumbnail_url,
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
    background_tasks.add_task(_execute_global_keyword_sourcing_bg, payload.keywords, float(payload.min_margin))
    
    return {"status": "accepted", "message": f"Global keyword sourcing started for {len(payload.keywords)} keywords"}


@router.post("/evaluate-keyword", response_model=KeywordEvaluateOut)
def evaluate_keyword_policy(
    payload: KeywordEvaluateIn,
    session: Session = Depends(get_session)
):
    """
    특정 키워드에 대한 쿠팡 소싱 정책(등급, 점수, 분석 사유)을 평가합니다.
    UI에서 소싱 시작 전 키워드 정보를 미리 확인하는 용도로 사용합니다.
    """
    from app.services.analytics.coupang_policy import CoupangSourcingPolicyService
    
    result = CoupangSourcingPolicyService.evaluate_keyword_policy(session, payload.keyword)
    return result

async def _execute_global_keyword_sourcing_bg(keywords: list[str], min_margin: float) -> None:
    await anyio.to_thread.run_sync(_execute_global_keyword_sourcing, keywords, min_margin)

def _execute_global_keyword_sourcing(keywords: list[str], min_margin: float) -> None:
    import asyncio
    import traceback
    from app.session_factory import session_factory
    from app.services.sourcing_service import SourcingService

    try:
        with session_factory() as session:
            service = SourcingService(session)
            async def _run_all() -> None:
                if isinstance(keywords, str):
                    await service.execute_keyword_sourcing(keywords, float(min_margin))
                    return
                for keyword in keywords:
                    await service.execute_keyword_sourcing(keyword, float(min_margin))

            anyio.run(_run_all)
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
            # execute_benchmark_sourcing이 내부적으로 비동기이면 anyio.run 사용, 
            # 여기서는 API가 블로킹되지 않도록 to_thread 진입점에서 이미 분리됨
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


async def _execute_benchmark_sourcing_bg(benchmark_id: uuid.UUID, job_id: uuid.UUID) -> None:
    # 오래 걸리는 소싱 작업(DB I/O, API 호출)을 블로킹 없이 처리하기 위해 스레드 오프로딩
    await anyio.to_thread.run_sync(_execute_benchmark_sourcing_sync_wrapper, benchmark_id, job_id)

def _execute_benchmark_sourcing_sync_wrapper(benchmark_id: uuid.UUID, job_id: uuid.UUID) -> None:
    anyio.run(_execute_benchmark_sourcing, benchmark_id, job_id)


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
    session.commit()

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

    try:
        raw_item = get_or_fetch_ownerclan_item_raw(
            session,
            item_code=str(candidate.supplier_item_id or ""),
            force_fetch=bool(payload.forceFetchOwnerClan),
        )
    except OwnerClanItemError as exc:
        if exc.code == "missing_primary_account":
            detail = "오너클랜(seller) 대표 계정이 설정되어 있지 않습니다"
        elif exc.code == "fetch_failed":
            http_status = exc.meta.get("http_status")
            detail = (
                f"오너클랜 상품 조회 실패: HTTP {http_status}"
                if http_status is not None
                else "오너클랜 상품 조회 실패"
            )
        else:
            detail = "오너클랜 상품 조회 실패"
        raise HTTPException(status_code=exc.status_code, detail=detail)
    if not raw_item:
        raise HTTPException(status_code=404, detail="오너클랜 raw item을 찾을 수 없습니다")

    product, created, _updated = create_or_get_product_from_raw_item(session, raw_item)

    effective_auto_process = bool(payload.autoProcess) or bool(payload.autoRegisterCoupang)

    if effective_auto_process:
        background_tasks.add_task(
            _execute_post_promote_actions_bg,
            product.id,
            bool(payload.autoRegisterCoupang),
            int(payload.minImagesRequired),
        )

    session.commit()

    return {
        "created": bool(created),
        "productId": str(product.id),
        "autoProcess": bool(effective_auto_process),
        "autoRegisterCoupang": bool(payload.autoRegisterCoupang),
    }
