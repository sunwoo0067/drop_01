import sys
import os
import asyncio
import logging

# Add app to path
sys.path.append(os.getcwd())

from app.services.ai.service import AIService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_rnj1_sourcing_strategy():
    logger.info("Initializing AIService...")
    ai_service = AIService()
    
    market_trends = """
    2026년 초 트렌드:
    1. 친환경 소재를 활용한 홈 오피스 가구 수요 급증 (대나무, 재생 플라스틱 등)
    2. 소형 가전의 개인화 및 디자인 중시 (MZ세대를 겨냥한 레트로 디자인)
    3. 반려동물용 프리미엄 스마트 헬스케어 기기 시장 확대
    4. 고령화 사회 진입에 따른 시니어용 '이지-케어' 주방 도구 관심 증가
    """
    
    existing_products = [
        "기본형 논슬립 옷걸이",
        "심플 디자인 탁상 조명",
        "반려동물 자동 급식기 (기본형)",
        "스테인리스 텀블러"
    ]
    
    logger.info("Requesting sourcing strategy from RNJ-1 (Reasoning Model)...")
    logger.info("Note: This may take a while depending on the model's complexity.")
    
    # Force use of ollama for this test
    strategy = ai_service.suggest_sourcing_strategy(
        market_trends=market_trends,
        existing_products=existing_products,
        provider="ollama"
    )
    
    if strategy:
        print("\n" + "="*50)
        print("RNJ-1 SUGGESTED SOURCING STRATEGY")
        print("="*50)
        print(strategy)
        print("="*50 + "\n")
    else:
        logger.error("Failed to get strategy from RNJ-1.")

if __name__ == "__main__":
    asyncio.run(test_rnj1_sourcing_strategy())
