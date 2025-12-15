from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session
import uuid

from app.db import get_session
from app.services.sourcing_service import SourcingService

router = APIRouter()

class KeywordSourceIn(BaseModel):
    keywords: List[str]
    min_margin: float = 0.15

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
