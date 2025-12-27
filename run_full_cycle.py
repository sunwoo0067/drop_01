import asyncio
import logging
from app.db import get_session
from app.services.orchestrator_service import OrchestratorService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_full_cycle():
    logger.info("Starting Full AI Orchestration Cycle via runner script...")
    
    session_gen = get_session()
    db = next(session_gen)
    
    try:
        orchestrator = OrchestratorService(db)
        # dry_run=False로 호출하여 실제 등록 진행
        strategy = await orchestrator.run_daily_cycle(dry_run=False)
        logger.info(f"Cycle completed. Strategic theme: {strategy.get('strategy_theme')}")
    except Exception as e:
        logger.exception(f"Fatal error during orchestration cycle: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run_full_cycle())
