import asyncio
import logging
import sys
import os

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.getcwd())

from app.db import get_session
from app.services.orchestrator_service import OrchestratorService
from app.models import SystemSetting

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    logger.info("Manual Continuous Processing Worker Starter")
    db = next(get_session())
    orchestrator = OrchestratorService(db)
    
    # 워커 기동
    try:
        await orchestrator.run_continuous_processing()
    except Exception as e:
        logger.error(f"Worker crashed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(main())
