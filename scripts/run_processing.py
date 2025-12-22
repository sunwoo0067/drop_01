import sys
import os
import logging
import asyncio

# Add app to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.db import SessionLocal
from app.services.processing_service import ProcessingService

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting Product Processing Job...")
    
    db = SessionLocal()
    try:
        service = ProcessingService(db)
        
        # Process up to 50 pending items
        processed_count = await service.process_pending_products(limit=50)
        
        logger.info(f"Job Complete. Processed {processed_count} products.")
        
    except Exception as e:
        logger.error(f"Job Failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(main())
