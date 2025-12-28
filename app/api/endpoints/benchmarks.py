from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session
import uuid
import asyncio
import logging
from datetime import datetime, timezone

from app.db import get_session
from app.models import BenchmarkCollectJob, BenchmarkProduct
from app.benchmark.collector_factory import get_benchmark_collector, get_supported_market_codes

logger = logging.getLogger(__name__)

router = APIRouter()


class BenchmarkRankingCollectIn(BaseModel):
    marketCode: str = "COUPANG"
    categoryUrl: str | None = None
    limit: int = 10


def _to_iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.isoformat()


@router.get("/")
def list_benchmarks(
    session: Session = Depends(get_session),
    q: str | None = Query(default=None),
    market_code: str | None = Query(default=None, alias="marketCode"),
    order_by: str | None = Query(default=None, alias="orderBy"),
    min_price: float | None = Query(default=None, alias="minPrice"),
    max_price: float | None = Query(default=None, alias="maxPrice"),
    min_review_count: int | None = Query(default=None, alias="minReviewCount"),
    min_rating: float | None = Query(default=None, alias="minRating"),
    min_quality_score: float | None = Query(default=None, alias="minQualityScore"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    order_key = (order_by or "created").strip().lower()
    if order_key == "updated":
        stmt = (
            select(BenchmarkProduct)
            .order_by(BenchmarkProduct.updated_at.desc(), BenchmarkProduct.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    else:
        stmt = (
            select(BenchmarkProduct)
            .order_by(BenchmarkProduct.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

    filters = []
    if market_code:
        filters.append(BenchmarkProduct.market_code == market_code)
    if q:
        like = f"%{q}%"
        filters.append(BenchmarkProduct.name.ilike(like))
    if min_price is not None:
        filters.append(BenchmarkProduct.price >= min_price)
    if max_price is not None:
        filters.append(BenchmarkProduct.price <= max_price)
    if min_review_count is not None:
        filters.append(BenchmarkProduct.review_count >= min_review_count)
    if min_rating is not None:
        filters.append(BenchmarkProduct.rating >= min_rating)
    if min_quality_score is not None:
        filters.append(BenchmarkProduct.quality_score >= min_quality_score)

    for condition in filters:
        stmt = stmt.where(condition)

    count_stmt = select(func.count()).select_from(BenchmarkProduct)
    for condition in filters:
        count_stmt = count_stmt.where(condition)

    rows = session.scalars(stmt).all()
    total = session.execute(count_stmt).scalar() or 0
    result: list[dict] = []
    for row in rows:
        rawData = row.raw_data if isinstance(row.raw_data, dict) else {}
        rawHtmlVal = rawData.get("raw_html")
        result.append(
            {
                "id": str(row.id),
                "marketCode": row.market_code,
                "productId": row.product_id,
                "name": row.name,
                "price": row.price,
                "productUrl": row.product_url,
                "imageUrls": row.image_urls,
                "detailHtmlLen": len(row.detail_html or ""),
                "rawHtmlLen": len(rawHtmlVal) if isinstance(rawHtmlVal, str) else 0,
                "blockedReason": rawData.get("blocked_reason"),
                "reviewSummary": row.review_summary,
                "painPoints": row.pain_points,
                "createdAt": row.created_at.isoformat() if row.created_at else None,
                "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
            }
        )
    return {"items": result, "total": total}


@router.get("/jobs/{job_id}")
def get_benchmark_collect_job(job_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    job = session.get(BenchmarkCollectJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="벤치마크 수집 job을 찾을 수 없습니다")

    return {
        "id": str(job.id),
        "status": job.status,
        "marketCode": job.market_code,
        "markets": job.markets,
        "limit": job.limit,
        "categoryUrl": job.category_url,
        "progress": job.progress,
        "processedCount": job.processed_count,
        "totalCount": job.total_count,
        "failedMarkets": job.failed_markets,
        "lastError": job.last_error,
        "params": job.params,
        "startedAt": _to_iso(job.started_at),
        "finishedAt": _to_iso(job.finished_at),
        "createdAt": _to_iso(job.created_at),
        "updatedAt": _to_iso(job.updated_at),
    }


@router.get("/jobs")
def list_benchmark_collect_jobs(
    session: Session = Depends(get_session),
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    stmt = (
        select(BenchmarkCollectJob)
        .order_by(BenchmarkCollectJob.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    total_stmt = select(func.count()).select_from(BenchmarkCollectJob)
    jobs = session.scalars(stmt).all()
    total = session.execute(total_stmt).scalar() or 0
    items = [
        {
            "id": str(j.id),
            "status": j.status,
            "marketCode": j.market_code,
            "markets": j.markets,
            "limit": j.limit,
            "categoryUrl": j.category_url,
            "progress": j.progress,
            "processedCount": j.processed_count,
            "totalCount": j.total_count,
            "failedMarkets": j.failed_markets,
            "lastError": j.last_error,
            "startedAt": _to_iso(j.started_at),
            "finishedAt": _to_iso(j.finished_at),
            "createdAt": _to_iso(j.created_at),
            "updatedAt": _to_iso(j.updated_at),
        }
        for j in jobs
    ]
    return {"items": items, "total": total}


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_benchmark_collect_job(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    job = session.get(BenchmarkCollectJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="벤치마크 수집 job을 찾을 수 없습니다")
    if job.status in ("queued", "running"):
        raise HTTPException(status_code=409, detail="해당 작업은 이미 진행 중입니다")

    limit = job.limit
    category_url = job.category_url or (job.params or {}).get("categoryUrl")
    markets = job.markets or [job.market_code]
    market_code = job.market_code

    if market_code.strip().upper() == "ALL":
        total_markets = len(markets) or 1
        new_job = BenchmarkCollectJob(
            status="queued",
            market_code="ALL",
            markets=markets,
            limit=limit,
            progress=0,
            category_url=None,
            processed_count=0,
            total_count=limit * total_markets,
            failed_markets=[],
            last_error=None,
            params={"categoryUrl": None},
        )
        session.add(new_job)
        session.flush()
        background_tasks.add_task(_execute_benchmark_all_ranking_collection, new_job.id, markets, limit)
    else:
        new_job = BenchmarkCollectJob(
            status="queued",
            market_code=market_code,
            markets=markets,
            limit=limit,
            progress=0,
            category_url=category_url,
            processed_count=0,
            total_count=limit,
            failed_markets=[],
            last_error=None,
            params={"categoryUrl": category_url},
        )
        session.add(new_job)
        session.flush()
        background_tasks.add_task(_execute_benchmark_ranking_collection, new_job.id, market_code, category_url, limit)

    return {
        "status": "accepted",
        "jobId": str(new_job.id),
        "marketCode": new_job.market_code,
        "categoryUrl": new_job.category_url,
        "limit": new_job.limit,
    }


@router.get("/{benchmark_id}")
def get_benchmark(benchmark_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    row = session.get(BenchmarkProduct, benchmark_id)
    if not row:
        raise HTTPException(status_code=404, detail="벤치마크 상품을 찾을 수 없습니다")

    rawData = row.raw_data if isinstance(row.raw_data, dict) else {}
    rawDataToReturn = dict(rawData)
    rawHtmlVal = rawDataToReturn.get("raw_html")
    rawHtmlLen = len(rawHtmlVal) if isinstance(rawHtmlVal, str) else 0
    rawHtmlTruncated = False
    if isinstance(rawHtmlVal, str) and len(rawHtmlVal) > 50000:
        rawDataToReturn["raw_html"] = rawHtmlVal[:50000]
        rawHtmlTruncated = True

    detailHtmlVal = row.detail_html
    detailHtmlLen = len(detailHtmlVal) if isinstance(detailHtmlVal, str) else 0
    detailHtmlTruncated = False
    detailHtmlToReturn = detailHtmlVal
    if isinstance(detailHtmlVal, str) and len(detailHtmlVal) > 200000:
        detailHtmlToReturn = detailHtmlVal[:200000]
        detailHtmlTruncated = True

    return {
        "id": str(row.id),
        "marketCode": row.market_code,
        "productId": row.product_id,
        "name": row.name,
        "price": row.price,
        "productUrl": row.product_url,
        "imageUrls": row.image_urls,
        "detailHtml": detailHtmlToReturn,
        "detailHtmlLen": detailHtmlLen,
        "detailHtmlTruncated": detailHtmlTruncated,
        "rawHtmlLen": rawHtmlLen,
        "rawHtmlTruncated": rawHtmlTruncated,
        "blockedReason": rawData.get("blocked_reason"),
        "rawData": rawDataToReturn,
        "reviewSummary": row.review_summary,
        "painPoints": row.pain_points,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.post("/collect/ranking", status_code=202)
async def collect_benchmark_ranking(
    payload: BenchmarkRankingCollectIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    market_code = str(payload.marketCode or "COUPANG").strip() or "COUPANG"
    category_url = str(payload.categoryUrl).strip() if payload.categoryUrl else None
    limit = int(payload.limit or 0)
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit은 1 이상이어야 합니다")

    if market_code.strip().upper() == "ALL":
        markets = get_supported_market_codes()
        total_markets = len(markets) or 1
        job = BenchmarkCollectJob(
            status="queued",
            market_code="ALL",
            markets=markets,
            limit=limit,
            progress=0,
            category_url=None,
            processed_count=0,
            total_count=limit * total_markets,
            failed_markets=[],
            last_error=None,
            params={"categoryUrl": None},
        )
        session.add(job)
        session.flush()

        background_tasks.add_task(_execute_benchmark_all_ranking_collection, job.id, markets, limit)
        return {"status": "accepted", "jobId": str(job.id), "marketCode": "ALL", "markets": markets, "limit": limit}

    job = BenchmarkCollectJob(
        status="queued",
        market_code=market_code,
        markets=[market_code],
        limit=limit,
        progress=0,
        category_url=category_url,
        processed_count=0,
        total_count=limit,
        failed_markets=[],
        last_error=None,
        params={"categoryUrl": category_url},
    )
    session.add(job)
    session.flush()

    background_tasks.add_task(_execute_benchmark_ranking_collection, job.id, market_code, category_url, limit)
    return {"status": "accepted", "jobId": str(job.id), "marketCode": market_code, "categoryUrl": category_url, "limit": limit}


def _execute_benchmark_ranking_collection(job_id: uuid.UUID, market_code: str, category_url: str | None, limit: int) -> None:
    from app.session_factory import session_factory

    with session_factory() as job_session:
        job = job_session.get(BenchmarkCollectJob, job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.progress = 0
        job.processed_count = 0
        job.total_count = job.total_count or limit
        job_session.commit()

    failed: list[str] = []
    last_error: str | None = None
    try:
        collector = get_benchmark_collector(market_code)
        asyncio.run(collector.run_ranking_collection(limit=limit, category_url=category_url))
    except Exception as e:
        logger.exception(f"벤치마크 수집 실패: marketCode={market_code}: {e}")
        failed.append(market_code)
        last_error = str(e)

    with session_factory() as job_session:
        job = job_session.get(BenchmarkCollectJob, job_id)
        if not job:
            return
        job.progress = 100
        job.processed_count = 0 if failed else (job.total_count or limit)
        job.failed_markets = failed
        job.last_error = last_error
        job.status = "succeeded"
        job.finished_at = datetime.now(timezone.utc)
        job_session.commit()


def _execute_benchmark_all_ranking_collection(job_id: uuid.UUID, market_codes: list[str], limit: int) -> None:
    from app.session_factory import session_factory

    with session_factory() as job_session:
        job = job_session.get(BenchmarkCollectJob, job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.progress = 0
        job.failed_markets = []
        job.last_error = None
        job.processed_count = 0
        job.total_count = job.total_count or (limit * max(len(market_codes), 1))
        job_session.commit()

    async def _run_all() -> tuple[list[str], str | None, int]:
        failed_markets: list[str] = []
        last_error: str | None = None

        total = max(len(market_codes), 1)
        processed = 0
        for idx, code in enumerate(market_codes):
            try:
                collector = get_benchmark_collector(code)
                await collector.run_ranking_collection(limit=limit, category_url=None)
                processed += limit
            except Exception as e:
                logger.exception(f"벤치마크 ALL 수집 실패: marketCode={code}: {e}")
                failed_markets.append(code)
                last_error = str(e)

                last_error = str(e)
            progress = int(((idx + 1) / total) * 100)
            with session_factory() as inner_session:
                job = inner_session.get(BenchmarkCollectJob, job_id)
                if job:
                    job.progress = progress
                    job.processed_count = processed
                    job.failed_markets = failed_markets
                    job.last_error = last_error
                    inner_session.commit()

            await asyncio.sleep(1)

        return failed_markets, last_error, processed

    failed, last_error, processed = asyncio.run(_run_all())

    with session_factory() as job_session:
        job = job_session.get(BenchmarkCollectJob, job_id)
        if not job:
            return
        job.status = "succeeded"
        job.progress = 100
        job.processed_count = processed
        job.failed_markets = failed
        job.last_error = last_error
        job.finished_at = datetime.now(timezone.utc)
        job_session.commit()
