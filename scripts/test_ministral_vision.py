import sys
import os
import asyncio
import logging
import requests

# Add app to path
sys.path.append(os.getcwd())

from app.services.ai.service import AIService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_ministral_vision():
    logger.info("Initializing AIService...")
    ai_service = AIService()
    
    # Use a sample image from the web or a local file if exists
    # For PoC, let's try to find an image in the project or use a placeholder
    image_url = "https://images.unsplash.com/photo-1542291026-7eec264c27ff" # Sample sneaker image
    logger.info(f"Downloading sample image from {image_url}...")
    
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        image_data = response.content
    except Exception as e:
        logger.error(f"Failed to download sample image: {e}")
        return

    logger.info("Requesting image description from Ministral 3B (Vision)...")
    description = ai_service.describe_image(
        image_data=image_data,
        prompt="이 이미지에 있는 상품의 디자인, 색상, 소재, 그리고 느껴지는 브랜드 분위기를 한국어로 상세히 설명해주세요.",
        provider="ollama"
    )
    
    if description:
        print("\n" + "="*50)
        print("MINISTRAL 3B VISION DESCRIPTION")
        print("="*50)
        print(description)
        print("="*50 + "\n")
    else:
        logger.error("Failed to get description from Ministral 3B.")

if __name__ == "__main__":
    asyncio.run(test_ministral_vision())
