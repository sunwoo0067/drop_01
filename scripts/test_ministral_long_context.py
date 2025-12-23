import sys
import os
import asyncio
import logging

# Add app to path
sys.path.append(os.getcwd())

from app.services.ai.service import AIService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_ministral_long_context():
    logger.info("Initializing AIService...")
    ai_service = AIService()
    
    # Create a very long text (around 50,000 chars)
    # Repeating a product description many times
    base_text = """
    [프리미엄 로봇 청소기 X-100]
    주요 기능:
    - 강력한 5000Pa 흡입력
    - LiDAR 4.0 센서를 이용한 고정밀 맵핑
    - 자동 먼지 비움 및 물걸레 세척 시스템
    - AI 사물 인식 (전선, 반려동물 배설물 등 회피)
    - 5200mAh 대용량 배터리 (최대 180분 가동)
    - 스마트폰 앱 연동 (구역 지정, 예약 청소)
    - 저소음 설계 (최저 55dB)
    - 카펫 인식 자동 흡입력 강화
    
    상세 설명:
    이 제품은 최첨단 기술이 집약된 프리미엄 로봇 청소기입니다. 
    기존 모델 대비 2배 강력해진 흡입력으로 미세먼지부터 큰 부스러기까지 완벽하게 제거합니다.
    특히 이번 LiDAR 4.0 센서는 초당 2000회 스캔을 통해 복잡한 가정 환경에서도 
    단 한번의 부딪힘 없이 완벽한 경로를 생성합니다.
    ... (중략) ...
    """
    
    # Let's add a "Hidden Spec" at the very end to check if it reads everything
    hidden_spec = "특이사항: 본 제품은 한정판 '티타늄 실버' 모델에만 샴페인 골드 브러시가 탑재됩니다."
    
    long_text = (base_text * 100) + "\n\n" + hidden_spec
    logger.info(f"Input text length: {len(long_text)} characters.")

    logger.info("Requesting spec extraction from Ministral 3B (supporting 256k context)...")
    specs = ai_service.extract_specs(
        text=long_text,
        provider="ollama"
    )
    
    if specs:
        print("\n" + "="*50)
        print("MINISTRAL 3B LONG CONTEXT SPEC EXTRACTION")
        print("="*50)
        import json
        print(json.dumps(specs, indent=2, ensure_ascii=False))
        
        if "특이사항" in str(specs) or "titanium_silver" in str(specs) or "샴페인" in str(specs):
            print("\n[SUCCESS] Ministral 3B successfully read the hidden spec at the end of the long text!")
        else:
            print("\n[WARNING] Hidden spec not found in extracted output.")
        print("="*50 + "\n")
    else:
        logger.error("Failed to extract specs from long text.")

if __name__ == "__main__":
    asyncio.run(test_ministral_long_context())
