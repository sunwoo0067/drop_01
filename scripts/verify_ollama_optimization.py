import sys
import os
import asyncio
import logging
import json

# Add app to path
sys.path.append(os.getcwd())

from app.services.ai.service import AIService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_optimized_ollama():
    logger.info("Initializing AIService with optimized Ollama (Chat API + Custom Model)...")
    ai_service = AIService()
    
    # 1. Test Vision with custom model (drop-vision)
    logger.info("Testing Vision with custom model 'drop-vision'...")
    from scripts.test_ministral_vision import test_ministral_vision
    # We can just reuse the logic but verify through AIService
    import requests
    response = requests.get("https://images.unsplash.com/photo-1542291026-7eec264c27ff")
    image_data = response.content
    
    desc = ai_service.describe_image(image_data, provider="ollama")
    print("\n[VISION RESULT]\n", desc[:500], "...")

    # 2. Test Long Context Tool Extraction
    logger.info("Testing Long Context extraction with Native JSON mode...")
    long_text = "상품 설명 " * 2000 + "\n\n특이사항: 본 제품은 우주 항공 등급 알루미늄으로 제작되었습니다."
    specs = ai_service.extract_specs(long_text, provider="ollama")
    
    print("\n[SPECS RESULT]\n", json.dumps(specs, indent=2, ensure_ascii=False))
    
    if "우주" in str(specs) or "알루미늄" in str(specs):
        print("\n[SUCCESS] Long context and Persona-based extraction verified!")
    else:
        print("\n[WARNING] Spec extraction might have context limit issues.")

if __name__ == "__main__":
    asyncio.run(verify_optimized_ollama())
