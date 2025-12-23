from fastapi import APIRouter, Depends, BackgroundTasks, Query
from sqlalchemy.orm import Session
import logging
from app.db import get_session
from app.services.orchestrator_service import OrchestratorService

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/run-cycle", status_code=202)
async def trigger_daily_cycle(
    background_tasks: BackgroundTasks,
    dry_run: bool = Query(default=True, alias="dryRun"),
    session: Session = Depends(get_session),
):
    """
    AI 오케스트레이션 데일리 사이클(Sourcing -> Step 1 Listing)을 실행합니다.
    """
    orchestrator = OrchestratorService(session)
    
    async def _run():
        try:
            await orchestrator.run_daily_cycle(dry_run=dry_run)
        except Exception as e:
            logger.error(f"Error in triggered daily cycle: {e}")

    background_tasks.add_task(_run)
    return {"status": "accepted", "dryRun": dry_run}
