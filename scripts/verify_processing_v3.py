import asyncio
import logging
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.services.processing_service import ProcessingService
from app.models import Product
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_processing_high_level():
    db: Session = SessionLocal()
    try:
        processing_service = ProcessingService(db)
        
        # 1. 테스트용 임시 상품 생성 (혹은 기존 상품 검색)
        test_product = Product(
            id=uuid.uuid4(),
            name="[오너클랜] 캠핑용 접이식 의자 경량 알루미늄 체어",
            brand="캠핑마스터",
            description="상세페이지 내 텍스트가 부족한 상황을 가정합니다.",
            status="DRAFT",
            processing_status="PENDING"
        )
        db.add(test_product)
        db.commit()
        
        logger.info(f"--- 가공 검증 시작: {test_product.name} ---")
        
        # 테스트를 위한 이미지 추가 (OCR 테스트용)
        # 유효한 Unsplash 이미지 URL 사용 (Nike 신발 이미지 등)
        mock_images = [
            "https://images.unsplash.com/photo-1542291026-7eec264c27ff",
            "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9"
        ]
        
        # ProcessingService.process_product를 직접 호출하기 위해 
        # input_data를 조작하거나, DB의 SupplierItemRaw를 맞춰야 하지만
        # 여기서는 Agent를 직접 호출하여 로직만 검증합니다.
        
        input_data = {
            "name": test_product.name,
            "brand": test_product.brand,
            "description": test_product.description,
            "images": mock_images,
            "detail_html": "<div>테스트 상세 HTML</div>"
        }
        
        logger.info("[Test] Running ProcessingAgent directly...")
        result = await processing_service.processing_agent.run(str(test_product.id), input_data)
        
        output = result.get("final_output", {})
        logs = result.get("logs", [])
        
        logger.info("--- 가공 결과 ---")
        logger.info(f"원본 명칭: {test_product.name}")
        logger.info(f"가공 명칭: {output.get('processed_name')}")
        logger.info(f"키워드: {output.get('processed_keywords')}")
        logger.info(f"로그: {logs}")
        
        # 정합성 확인
        if output.get('processed_name') and output.get('processed_name') != test_product.name:
            logger.info("✅ SUCCESS: 상품명이 AI에 의해 최적화되었습니다.")
        else:
            logger.warning("⚠️ WARNING: 상품명이 변경되지 않았습니다. (이미 최적화 상태이거나 AI 미응답)")

        # DB 삭제 (테스트 데이터 정리)
        db.delete(test_product)
        db.commit()

    except Exception as e:
        logger.exception(f"검증 중 오류 발생: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(verify_processing_high_level())
