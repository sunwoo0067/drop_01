import asyncio
import logging
import uuid
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, func
from app.db import SessionLocal
from app.models import Product, SupplierItemRaw
from app.services.ai.agents.processing_agent import ProcessingAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_vlm_optimization():
    print("\n--- VLM-based Content Optimization Verification ---\n")
    
    with SessionLocal() as db:
        # 1. 이미지가 있는 STEP_2 또는 STEP_3 상품 찾기
        stmt = (
            select(Product)
            .where(Product.lifecycle_stage.in_(["STEP_2", "STEP_3"]))
            .where(Product.processed_image_urls != None)
            .limit(1)
        )
        product = db.scalars(stmt).first()
        
        if not product:
            logger.info("No product found. Creating test product...")
            product = Product(
                id=uuid.uuid4(),
                name="Test Chair",
                lifecycle_stage="STEP_3"
            )
            db.add(product)
            db.commit()

        # 테스트용 유효 이미지 URL 강제 주입
        product.processed_image_urls = ["https://images.unsplash.com/photo-1524758631624-e2822e304c36?auto=format&fit=crop&q=80&w=1000"]
        product.lifecycle_stage = "STEP_3"
        db.commit()
        db.refresh(product)

        print(f"Target Product ID: {product.id}")
        print(f"Original Name: {product.name}")
        print(f"Lifecycle Stage: {product.lifecycle_stage}")
        print(f"Images: {product.processed_image_urls[:1] if product.processed_image_urls else 'None'}")

        # 2. 에이전트 실행을 위한 입력 데이터 준비
        raw_images = []
        if product.supplier_item_id:
            raw_item = db.get(SupplierItemRaw, product.supplier_item_id)
            if raw_item and isinstance(raw_item.raw, dict):
                raw = raw_item.raw
                images_val = raw.get("images")
                if isinstance(images_val, list):
                    raw_images = images_val[:3]
        
        if not raw_images and product.processed_image_urls:
            raw_images = product.processed_image_urls[:3]

        input_data = {
            "name": product.name,
            "brand": product.brand or "브랜드없음",
            "description": product.description or "",
            "images": raw_images,
            "category": getattr(product, "processed_category", "일반"),
            "target_market": "Coupang",
        }

        agent = ProcessingAgent(db)
        
        print("\nRunning VLM Optimization (ProcessingAgent)...")
        try:
            # SEO 최적화 노드 포함 실행
            result = await agent.run(str(product.id), input_data, verbose=True)
            
            print("\n--- Optimization Result ---")
            print(f"Status: {result.status}")
            
            output = result.final_output
            if output:
                print(f"Processed Name: {output.get('processed_name')}")
                print(f"Keywords: {output.get('processed_keywords')}")
                
                # 원본과 비교하여 얼마나 바뀌었는지 확인 (이미지 데이터 기반인지 판단 척도)
                if product.name != output.get('processed_name'):
                    print("\n[SUCCESS] AI optimized the product name.")
                else:
                    print("\n[NOTE] AI kept the original name or optimization didn't result in a change.")
            else:
                print("No final output received from agent.")
                if result.error_message:
                    print(f"Error: {result.error_message}")
                    
        except Exception as e:
            logger.error(f"Verification failed: {e}")

if __name__ == "__main__":
    asyncio.run(verify_vlm_optimization())
