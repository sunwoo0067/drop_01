import asyncio
import logging
import uuid
import sys
import os

# 프로젝트 루트 디렉토리를 sys.path에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models import Product, SourcingCandidate
from app.services.ai.agents.processing_agent import ProcessingAgent
from app.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_premium_branding():
    db = SessionLocal()
    agent = ProcessingAgent(db=db)
    
    try:
        # 1. 테스트용 상품 검색
        product = db.query(Product).filter(Product.processed_image_urls.isnot(None)).first()
        
        test_images = ["https://images.unsplash.com/photo-1592078615290-033ee584e267?q=80&w=1000&auto=format&fit=crop"]

        if not product:
            logger.info("No product found. Creating a test product...")
            product = Product(
                id=uuid.uuid4(),
                name="[Test] Premium Ergonomic Office Chair",
                processed_name="Premium Ergonomic Office Chair",
                processed_image_urls=test_images,
                lifecycle_stage="STEP_3"
            )
            db.add(product)
            db.commit()
            db.refresh(product)
        else:
            logger.info(f"Using existing product {product.id} (name: {product.name}) and setting to STEP_3")
            product.lifecycle_stage = "STEP_3"
            if not product.processed_image_urls:
                product.processed_image_urls = test_images
            db.commit()

        input_data = {
            "name": product.name,
            "images": product.processed_image_urls,
            "category": "Furniture/Chair",
            "detail_html": "<div>Premium office chair description...</div>"
        }

        logger.info(f"--- Starting Premium Branding Pipeline for {product.id} ---")
        
        # 2. ProcessingAgent 실행 (STEP 3 로직 포함)
        # process_images 노드만 테스트하고 싶지만, 전체 흐름 확인을 위해 process_by_lifecycle_stage 호출
        result = await agent.process_by_lifecycle_stage(
            target_id=str(product.id),
            input_data=input_data
        )

        # 3. 결과 확인
        if "errors" in result and result["errors"]:
            logger.error(f"Pipeline failed with errors: {result['errors']}")
            return

        final_output = result.get("final_output", {})
        processed_images = final_output.get("processed_image_urls", [])
        logs = result.get("logs", [])

        logger.info("\n=== Verification Results ===")
        for log in logs:
            logger.info(f"LOG: {log}")
            
        if len(processed_images) > len(input_data["images"]):
            logger.info(f"SUCCESS: Premium image generated! Total images: {len(processed_images)}")
            logger.info(f"Premium Main Image URL: {processed_images[0]}")
            logger.info(f"Original Base Images count: {len(processed_images) - 1}")
        else:
            logger.warning("FAILED: Premium image was not added to the list.")
            logger.info(f"Processed images count: {len(processed_images)}")

    except Exception as e:
        logger.error(f"Verification failed with exception: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(verify_premium_branding())
