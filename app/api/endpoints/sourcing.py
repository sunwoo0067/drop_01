from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session
import uuid
from sqlalchemy import select

from app.db import get_session
from app.services.sourcing_service import SourcingService
from app.models import SourcingCandidate

router = APIRouter()

class KeywordSourceIn(BaseModel):
    keywords: List[str]
    min_margin: float = 0.15

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
        "status": row.status,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
    }

@router.post("/keyword")
async def trigger_keyword_sourcing(
    payload: KeywordSourceIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """
    Triggers sourcing based on a list of keywords.
    Runs in background.
    """
    service = SourcingService(session)
    # We run it in background to avoid blocking
    background_tasks.add_task(service.execute_keyword_sourcing, payload.keywords, payload.min_margin)
    return {"status": "accepted", "message": f"Global keyword sourcing started for {len(payload.keywords)} keywords"}

@router.post("/benchmark/{benchmark_id}")
async def trigger_benchmark_sourcing(
    benchmark_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """
    Triggers smart sourcing based on a Benchmark Product (Gap Analysis, Spec Matching).
    Runs in background.
    """
    service = SourcingService(session)
    background_tasks.add_task(service.execute_benchmark_sourcing, benchmark_id)
    return {"status": "accepted", "message": f"Benchmark sourcing started for {benchmark_id}"}
