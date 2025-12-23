import sys
import os
import logging
import asyncio
from typing import List

# Add app to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.db import SessionLocal
from app.services.processing_service import ProcessingService

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("mass_process_ai")

async def process_batch(limit: int = 100):
    db = SessionLocal()
    try:
        service = ProcessingService(db)
        # process_pending_products는 내부적으로 limit만큼 가져와서 순차 처리함
        # 속도를 위해 10개씩 끊어서 여러 번 호출하거나, 내부 로직을 병렬화할 수 있지만
        # 리소스(Ollama/GPU) 제약을 고려하여 안전하게 순차 대량 처리
        
        total_processed = 0
        batch_size = 50
        
        while total_processed < limit:
            current_limit = min(batch_size, limit - total_processed)
            logger.info(f"Processing next batch of {current_limit} (Total processed: {total_processed}/{limit})")
            
            processed_count = await service.process_pending_products(limit=current_limit)
            if processed_count == 0:
                logger.info("No more pending products to process.")
                break
                
            total_processed += processed_count
            logger.info(f"Successfully processed {processed_count} items in this batch.")
            
        logger.info(f"Mass Processing Complete. Total: {total_processed}")
        
    except Exception as e:
        logger.error(f"Mass Processing Failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    asyncio.run(process_batch(count))
