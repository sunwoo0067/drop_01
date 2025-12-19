import logging
import uuid
import json
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import Product, BenchmarkProduct
from app.services.ai.agents.processing_agent import ProcessingAgent
from app.services.image_processing import image_processing_service

logger = logging.getLogger(__name__)

class ProcessingService:
    def __init__(self, db: Session):
        self.db = db
        self.processing_agent = ProcessingAgent(db)

    async def process_product(self, product_id: uuid.UUID, min_images_required: int = 5) -> bool:
        """
        Orchestrates the processing of a single product using LangGraph ProcessingAgent.
        """
        try:
            logger.info(f"Starting LangGraph processing for product {product_id}...")
            
            product = self.db.scalars(select(Product).where(Product.id == product_id)).one_or_none()
            if not product:
                logger.error(f"Product {product_id} not found.") # Added this line back for better logging
                return False

            product.processing_status = "PROCESSING"
            self.db.commit()

            # 데이터 추출
            input_data = {
                "name": product.name,
                "brand": product.brand,
                "description": product.description,
                "images": [] # 실제 운영 환경에서는 raw item에서 가져옴
            }
            
            # 에이전트 실행
            result = await self.processing_agent.run(str(product_id), input_data)
            output = result.get("final_output", {})
            
            # 결과 반영
            product.processed_name = output.get("processed_name")
            product.processed_keywords = output.get("processed_keywords")
            product.processed_image_urls = output.get("processed_image_urls")
            
            if product.processed_image_urls and len(product.processed_image_urls) >= max(1, int(min_images_required)):
                product.processing_status = "COMPLETED"
            else:
                product.processing_status = "FAILED"
                
            self.db.commit()
            logger.info(f"Successfully processed product {product_id}. Status: {product.processing_status}") # Added this line back for better logging
            return True
            
        except Exception as e:
            logger.error(f"Error processing product {product_id}: {e}")
            self.db.rollback()
            try:
                # Try to key status as failed
                product.processing_status = "FAILED"
                self.db.commit()
            except:
                pass
            return False

    async def process_pending_products(self, limit: int = 10, min_images_required: int = 5):
        """
        Finds pending products and processes them.
        """
        stmt = select(Product).where(Product.processing_status == "PENDING").limit(limit)
        products = self.db.scalars(stmt).all()
        
        count = 0
        for p in products:
            if await self.process_product(p.id, min_images_required=min_images_required):
                count += 1
        return count
