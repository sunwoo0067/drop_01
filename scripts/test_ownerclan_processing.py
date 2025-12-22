import asyncio
import uuid
import logging
import sys
import os

# 프로젝트 루트를 path에 추가
sys.path.append(os.getcwd())

from app.db import SessionLocal
from app.models import Product, SupplierItemRaw
from app.services.processing_service import ProcessingService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_processing(product_id_str: str):
    product_id = uuid.UUID(product_id_str)
    session = SessionLocal()
    
    try:
        # 가공 전 상태 확인
        product = session.get(Product, product_id)
        if not product:
            print(f"Product {product_id} not found")
            return
        
        print(f"--- Before Processing ---")
        print(f"ID: {product.id}")
        print(f"Name: {product.name}")
        print(f"Processed Name: {product.processed_name}")
        print(f"Status: {product.processing_status}")
        print(f"Description Length: {len(product.description) if product.description else 0}")
        print(f"Image Count: {len(product.processed_image_urls) if product.processed_image_urls else 0}")
        
        # 가공 실행
        service = ProcessingService(session)
        print(f"\n--- Starting Processing ---")
        success = await service.process_product(product_id)
        print(f"Success: {success}")
        
        # 가공 후 상태 확인
        session.refresh(product)
        print(f"\n--- After Processing ---")
        print(f"Processed Name: {product.processed_name}")
        print(f"Status: {product.processing_status}")
        print(f"Description Length: {len(product.description) if product.description else 0}")
        print(f"Images: {product.processed_image_urls}")
        
    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    target_id = "98db96c4-637e-4d61-9598-8917ff62e1d8"
    if len(sys.argv) > 1:
        target_id = sys.argv[1]
    
    asyncio.run(test_processing(target_id))
