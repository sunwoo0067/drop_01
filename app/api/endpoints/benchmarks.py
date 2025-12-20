from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
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
    limit: int = Field(default=10, ge=1, le=50)


def _to_iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.isoformat()


@router.get("/")
def list_benchmarks(
    session: Session = Depends(get_session),
    q: str | None = Query(default=None),
    market_code: str | None = Query(default=None, alias="marketCode"),
    min_price: int | None = Query(default=None, alias="minPrice"),
    max_price: int | None = Query(default=None, alias="maxPrice"),
    min_review_count: int | None = Query(default=None, alias="minReviewCount"),
    min_rating: float | None = Query(default=None, alias="minRating"),
    min_quality_score: float | None = Query(default=None, alias="minQualityScore"),
    order_by: str | None = Query(default=None, alias="orderBy"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    stmt = select(BenchmarkProduct)
    
    # Filtering
    if market_code:
        stmt = stmt.where(BenchmarkProduct.market_code == market_code)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(BenchmarkProduct.name.ilike(like))
    if min_price is not None:
        stmt = stmt.where(BenchmarkProduct.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(BenchmarkProduct.price <= max_price)
    if min_review_count is not None:
        stmt = stmt.where(BenchmarkProduct.review_count >= min_review_count)
    if min_rating is not None:
        stmt = stmt.where(BenchmarkProduct.rating >= min_rating)
    if min_quality_score is not None:
        stmt = stmt.where(BenchmarkProduct.quality_score >= min_quality_score)

    # Count for pagination
    from sqlalchemy import func
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    # Ordering
    order_key = (order_by or "created").strip().lower()
    if order_key == "updated":
        stmt = stmt.order_by(BenchmarkProduct.updated_at.desc(), BenchmarkProduct.created_at.desc())
    elif order_key == "price_asc":
        stmt = stmt.order_by(BenchmarkProduct.price.asc())
    elif order_key == "price_desc":
        stmt = stmt.order_by(BenchmarkProduct.price.desc())
    elif order_key == "reviews":
        stmt = stmt.order_by(BenchmarkProduct.review_count.desc())
    elif order_key == "rating":
        stmt = stmt.order_by(BenchmarkProduct.rating.desc())
    elif order_key == "quality":
        stmt = stmt.order_by(BenchmarkProduct.quality_score.desc())
    else:
        stmt = stmt.order_by(BenchmarkProduct.created_at.desc())

    # Pagination
    stmt = stmt.offset(offset).limit(limit)
    rows = session.scalars(stmt).all()
    
    items: list[dict] = []
    for row in rows:
        rawData = row.raw_data if isinstance(row.raw_data, dict) else {}
        rawHtmlVal = rawData.get("raw_html")
        items.append(
            {
                "id": str(row.id),
                "marketCode": row.market_code,
                "productId": row.product_id,
                "name": row.name,
                "price": row.price,
                "productUrl": row.product_url,
                "imageUrls": row.image_urls,
                "categoryPath": row.category_path,
                "reviewCount": row.review_count,
                "rating": row.rating,
                "qualityScore": row.quality_score,
                "detailHtmlLen": len(row.detail_html or ""),
                "rawHtmlLen": len(rawHtmlVal) if isinstance(rawHtmlVal, str) else 0,
                "blockedReason": rawData.get("blocked_reason"),
                "reviewSummary": row.review_summary,
                "painPoints": row.pain_points,
                "createdAt": row.created_at.isoformat() if row.created_at else None,
                "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
            }
        )
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit
    }


@router.get("/jobs/{job_id}")
def get_benchmark_collect_job(job_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    job = session.get(BenchmarkCollectJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="벤치마크 수집 job을 찾을 수 없습니다")

    return {
        "id": str(job.id),
        "status": job.status,
        "marketCode": job.market_code,
        "categoryUrl": job.category_url,
        "totalCount": job.total_count,
        "processedCount": job.processed_count,
        "retryOfJobId": str(job.retry_of_job_id) if job.retry_of_job_id else None,
        "limit": job.limit,
        "progress": job.progress,
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
    status: str | None = Query(default=None),
    market_code: str | None = Query(default=None, alias="marketCode"),
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    stmt = select(BenchmarkCollectJob).order_by(BenchmarkCollectJob.created_at.desc())
    if status:
        stmt = stmt.where(BenchmarkCollectJob.status == status)
    if market_code:
        stmt = stmt.where(BenchmarkCollectJob.market_code == market_code)
    
    from sqlalchemy import func
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    
    jobs = session.scalars(stmt.offset(offset).limit(limit)).all()
    items = [
        {
            "id": str(j.id),
            "status": j.status,
            "marketCode": j.market_code,
            "categoryUrl": j.category_url,
            "totalCount": j.total_count,
            "processedCount": j.processed_count,
            "limit": j.limit,
            "progress": j.progress,
            "failedMarkets": j.failed_markets,
            "lastError": j.last_error,
            "startedAt": _to_iso(j.started_at),
            "finishedAt": _to_iso(j.finished_at),
            "createdAt": _to_iso(j.created_at),
            "updatedAt": _to_iso(j.updated_at),
        }
        for j in jobs
    ]
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit
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
        "categoryPath": row.category_path,
        "reviewCount": row.review_count,
        "rating": row.rating,
        "qualityScore": row.quality_score,
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
    market_code = str(payload.marketCode or "COUPANG").strip().upper() or "COUPANG"
    category_url = str(payload.categoryUrl).strip() if payload.categoryUrl else None
    limit = int(payload.limit or 0)
    
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit은 1 이상이어야 합니다")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit은 50 이하여야 합니다")

    requested_markets = []
    if market_code == "ALL":
        requested_markets = get_supported_market_codes()
    else:
        requested_markets = [market_code]

    job_ids = []
    for m in requested_markets:
        job = BenchmarkCollectJob(
            status="queued",
            market_code=m,
            category_url=category_url if m == market_code else None,
            limit=limit,
            total_count=limit,
            processed_count=0,
            progress=0,
            params={"categoryUrl": category_url if m == market_code else None},
        )
        session.add(job)
        session.flush()
        job_ids.append(str(job.id))
        background_tasks.add_task(_execute_benchmark_ranking_collection, job.id, m, job.category_url, limit)
    
    session.commit()
    
    return {
        "status": "accepted",
        "jobIds": job_ids,
        "marketCode": market_code,
        "limit": limit
    }


@router.post("/jobs/{job_id}/retry", status_code=202)
async def retry_benchmark_collect_job(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    old_job = session.get(BenchmarkCollectJob, job_id)
    if not old_job:
        raise HTTPException(status_code=404, detail="재시도할 Job을 찾을 수 없습니다")
    
    new_job = BenchmarkCollectJob(
        status="queued",
        market_code=old_job.market_code,
        category_url=old_job.category_url,
        limit=old_job.limit,
        total_count=old_job.limit,
        processed_count=0,
        progress=0,
        retry_of_job_id=old_job.id,
        params=old_job.params
    )
    session.add(new_job)
    session.flush()
    session.commit()

    background_tasks.add_task(
        _execute_benchmark_ranking_collection, 
        new_job.id, 
        new_job.market_code, 
        new_job.category_url, 
        new_job.limit
    )
    return {"status": "accepted", "jobId": str(new_job.id)}


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
        job.total_count = limit
        job_session.commit()

    failed_markets: list[str] = []
    last_error: str | None = None
    try:
        collector = get_benchmark_collector(market_code)
        # Use asyncio.run if not in an event loop, but BackgroundTasks might be already in one?
        # Typically background tasks in FastAPI are run in a threadpool if they are 'def' functions.
        asyncio.run(collector.run_ranking_collection(limit=limit, category_url=category_url, job_id=job_id))
    except Exception as e:
        logger.exception(f"벤치마크 수집 실패: marketCode={market_code}: {e}")
        failed_markets.append(market_code)
        last_error = f"벤치마크 수집 실패: {e}"

    with session_factory() as job_session:
        job = job_session.get(BenchmarkCollectJob, job_id)
        if not job:
            return
        job.progress = 100
        job.failed_markets = failed_markets
        job.last_error = last_error
        job.status = "failed" if failed_markets else "succeeded"
        job.finished_at = datetime.now(timezone.utc)
        job_session.commit()


# Removed _execute_benchmark_all_ranking_collection as we now create separate jobs for each market.
