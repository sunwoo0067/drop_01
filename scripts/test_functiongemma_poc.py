import sys
import os
import json
import logging

# Add app to path
sys.path.append(os.getcwd())

from app.services.ai import AIService
from app.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_functiongemma_poc():
    logger.info("Starting FunctionGemma PoC Test...")
    service = AIService()
    
    sample_text = """
    [프리미엄 무선 헤드폰]
    브랜드: 사운드마스터
    모델명: SM-X100
    특징:
    - 하이브리드 노이즈 캔슬링 지원
    - 블루투스 5.3 기술 적용
    - 최대 40시간 재생 가능 (NC On 상태)
    - 무게: 250g
    - 충전방식: USB-C 타입 (고속 충전 지원)
    - 색상: 미드나이트 블랙, 스털링 실버
    - 주파수 응답: 20Hz - 20kHz
    - 드라이버 유닛: 40mm 고해상도 다이나믹 드라이버
    """
    
    logger.info("--- Testing Extract Specs with FunctionGemma ---")
    try:
        # 서비스 설정을 통해 이미 OllamaProvider는 functiongemma 모델을 사용하도록 설정됨
        specs = service.extract_specs(sample_text, provider="ollama")
        logger.info(f"Extracted Specs JSON:\n{json.dumps(specs, indent=2, ensure_ascii=False)}")
        
        # 기본 검증
        if "weight" in specs or "무게" in specs:
            logger.info("✅ Success: Weight information extracted.")
        if "brand" in specs or "브랜드" in specs:
            logger.info("✅ Success: Brand information extracted.")
            
    except Exception as e:
        logger.error(f"❌ Error during PoC: {e}")

    logger.info("--- Testing Pain Points Analysis ---")
    try:
        pain_points = service.analyze_pain_points(sample_text, provider="ollama")
        logger.info(f"Pain Points List: {pain_points}")
    except Exception as e:
        logger.error(f"❌ Error during Pain Points analysis: {e}")

if __name__ == "__main__":
    test_functiongemma_poc()
