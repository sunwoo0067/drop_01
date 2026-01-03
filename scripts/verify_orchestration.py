import asyncio
import logging
from app.db import SessionLocal
from app.services.orchestrator_service import OrchestratorService

# 로그 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def verify_orchestration():
    db = SessionLocal()
    try:
        orchestrator = OrchestratorService(db)
        
        print("\n" + "="*50)
        print("Starting Verification: AI Orchestration Daily Cycle")
        print("="*50)
        
        # 드라이 런 모드로 실행
        strategy = await orchestrator.run_daily_cycle(dry_run=True)
        
        print("\n" + "="*50)
        print("Verification Results:")
        print(f"Season: {strategy.get('season_name')}")
        print(f"Theme: {strategy.get('strategy_theme')}")
        print(f"Target Keywords: {strategy.get('target_keywords')[:5]}...")
        print(f"Outdated Keywords: {strategy.get('out_dated_keywords')[:5]}...")
        print("="*50)
        print("SUCCESS: Orchestration cycle executed (Dry-run). Check logs for details.")
        
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(verify_orchestration())
