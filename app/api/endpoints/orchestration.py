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
    
    async def _run_async_cycle():
        """비동기 실행 최적화: 서비스 인스턴스를 루프 내에서 생성"""
        from app.session_factory import session_factory
        from app.services.orchestrator_service import OrchestratorService
        import asyncio
        
        logger.info(f"Starting async orchestration cycle (dryRun={dry_run})")
        try:
            with session_factory() as session:
                orchestrator = OrchestratorService(session)
                
                # 병렬 실행 그룹화
                tasks = [orchestrator.run_daily_cycle(dry_run=dry_run)]
                
                # 드라이런이 아닐 경우 워커들 조기 가동 시도 (서비스 내부 로직과 병행)
                # 여기서는 run_daily_cycle이 메인으로 동작함
                await asyncio.gather(*tasks)
                logger.info("Daily cycle execution finished.")
        except Exception as e:
            logger.error(f"Critical error in async orchestration: {e}", exc_info=True)
            try:
                with session_factory() as session:
                    from app.models import OrchestrationEvent
                    event = OrchestrationEvent(step="SYSTEM", status="FAIL", message=f"시스템 오류: {str(e)[:100]}")
                    session.add(event)
                    session.commit()
            except: pass

    background_tasks.add_task(_run_async_cycle)
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


@router.get("/agents/status")
async def get_agents_status():
    """
    AI 에이전트들의 현재 상태를 가져옵니다.
    """
    from app.session_factory import session_factory
    from app.models import Product, SourcingCandidate
    from sqlalchemy import select, func
    
    with session_factory() as session:
        # Sourcing Agent 상태
        sourcing_pending = session.execute(
            select(func.count()).select_from(select(SourcingCandidate.id).where(SourcingCandidate.status == "PENDING").subquery())
        ).scalar() or 0
        
        # Processing Agent 상태
        processing_pending = session.execute(
            select(func.count()).select_from(select(Product.id).where(Product.processing_status == "PENDING").subquery())
        ).scalar() or 0
        
        return {
            "sourcing": {
                "status": "Healthy" if sourcing_pending > 0 else "Idle",
                "message": f"{sourcing_pending}개의 소싱 후보 대기 중" if sourcing_pending > 0 else "대기 중인 소싱 후보 없음",
                "queue_size": sourcing_pending
            },
            "processing": {
                "status": "Live" if processing_pending > 0 else "Idle",
                "message": f"{processing_pending}개의 상품 가공 대기 중" if processing_pending > 0 else "대기 중인 상품 없음",
                "queue_size": processing_pending
            }
        }
