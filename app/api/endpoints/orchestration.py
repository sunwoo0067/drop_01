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
):
    """
    AI 오케스트레이션 데일리 사이클(Sourcing -> Step 1 Listing)을 실행합니다.
    """
    logger.info(f"API called: /run-cycle?dryRun={dry_run}")
    
    def _run_wrapper():
        """동기 래퍼: FastAPI가 이를 별도 스레드에서 실행합니다."""
        import asyncio
        from app.session_factory import session_factory
        from app.services.orchestrator_service import OrchestratorService
        
        logger.info(f"Background thread started for cycle (dryRun={dry_run})")
        try:
            with session_factory() as session:
                orchestrator = OrchestratorService(session)
                # 시작 이벤트 기록 (이미 서비스 내부에서 하겠지만, 여기서도 예외 관리를 위해 감쌉니다)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(orchestrator.run_daily_cycle(dry_run=dry_run))
                    logger.info("Daily cycle completed successfully.")
                except Exception as cycle_error:
                    logger.error(f"Cycle execution error: {cycle_error}")
                    orchestrator._record_event("SYSTEM", "FAIL", f"작업 중 오류 발생: {str(cycle_error)[:100]}")
                finally:
                    loop.close()
        except Exception as e:
            logger.error(f"Critical error in background thread: {e}", exc_info=True)
            # 여기서는 세션이 없을 수 있으므로 직접 기록 시도
            try:
                with session_factory() as session:
                    from app.models import OrchestrationEvent
                    event = OrchestrationEvent(step="SYSTEM", status="FAIL", message=f"시스템 오류: {str(e)[:100]}")
                    session.add(event)
                    session.commit()
            except:
                pass

    background_tasks.add_task(_run_wrapper)
    logger.info("Background task dispatched to thread pool. Returning 202.")
    return {"status": "accepted", "dryRun": dry_run}


@router.get("/events")
async def get_orchestration_events(
    limit: int = Query(default=50, ge=1, le=100),
):
    """
    최근 오케스트레이션 이벤트 로그를 가져옵니다.
    """
    from app.session_factory import session_factory
    from app.models import OrchestrationEvent
    from sqlalchemy import select
    
    with session_factory() as session:
        stmt = select(OrchestrationEvent).order_by(OrchestrationEvent.created_at.desc()).limit(limit)
        events = session.execute(stmt).scalars().all()
        return events
