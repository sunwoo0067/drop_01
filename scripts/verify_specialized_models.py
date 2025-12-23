import asyncio
import logging
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.append(os.getcwd())

from app.services.ai import AIService
from app.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_models():
    ai_service = AIService()
    
    test_text = "이 상품은 프리미엄 블랙 티타늄 재질로 만들어졌으며, 크기는 150x50x20mm이고 무게는 120g입니다. 무선 충전을 지원하며 배터리 용량은 5000mAh입니다."
    test_image_url = "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500" # Simple watch image
    
    print("\n" + "="*50)
    print("🚀 Specialized Models Integration Verification")
    print("="*50)

    # 1. Spec Extraction (Expected: Granite 4)
    print("\n[1] Testing Spec Extraction (Logic Model: Granite 4)...")
    try:
        specs = ai_service.extract_specs(test_text, provider="ollama")
        print(f"✅ Result: {specs}")
    except Exception as e:
        print(f"❌ Failed: {e}")

    # 2. Seasonality Prediction (Expected: Granite 4)
    print("\n[2] Testing Seasonality Prediction (Logic Model: Granite 4)...")
    try:
        season = ai_service.predict_seasonality("블랙 티타늄 무선 보조배터리", provider="ollama")
        print(f"✅ Result: {season}")
    except Exception as e:
        print(f"❌ Failed: {e}")

    # 3. OCR (Expected: DeepSeek-OCR)
    print("\n[3] Testing OCR (Specialized OCR: DeepSeek-OCR)...")
    try:
        import requests
        resp = requests.get(test_image_url, timeout=10)
        if resp.status_code == 200:
            ocr_text = ai_service.extract_text_from_image(resp.content, format="text", provider="ollama")
            print(f"✅ Result: {ocr_text}")
        else:
            print("⚠️ Skipping OCR: Image download failed")
    except Exception as e:
        print(f"❌ Failed: {e}")

    # 4. Visual Layout Analysis (Expected: Qwen3-VL)
    print("\n[4] Testing Visual Layout Analysis (Spatial AI: Qwen3-VL)...")
    try:
        resp = requests.get(test_image_url, timeout=10)
        if resp.status_code == 200:
            layout = ai_service.analyze_visual_layout(resp.content, provider="ollama")
            print(f"✅ Result: {layout[:200]}...")
        else:
            print("⚠️ Skipping Layout: Image download failed")
    except Exception as e:
        print(f"❌ Failed: {e}")

    print("\n" + "="*50)
    print("✨ Verification Completed")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(verify_models())
