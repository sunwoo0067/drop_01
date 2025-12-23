import sys
import os
import asyncio
import logging
import base64
import requests

# Add app to path
sys.path.append(os.getcwd())

from app.services.ai.service import AIService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_deepseek_ocr():
    ai_service = AIService()
    
    # Sample image with text (Product Spec Table or similar)
    # Using a known sample image URL that contains text
    image_url = "https://images.unsplash.com/photo-1542291026-7eec264c27ff"
    
    try:
        logger.info(f"Downloading sample image for OCR: {image_url}")
        response = requests.get(image_url, timeout=10)
        image_data = response.content
    except Exception as e:
        logger.error(f"Failed to download image: {e}")
        return

    # 1. Plain Text Extraction
    logger.info("Test 1: Plain Text Extraction...")
    text_result = ai_service.extract_text_from_image(image_data, format="text", provider="ollama")
    print("\n[TEXT EXTRACTION]\n", text_result)

    # 2. Markdown Conversion (using <|grounding|>)
    logger.info("Test 2: Markdown Conversion...")
    md_result = ai_service.extract_text_from_image(image_data, format="markdown", provider="ollama")
    print("\n[MARKDOWN EXTRACTION]\n", md_result)

    # 3. JSON Extraction
    logger.info("Test 3: JSON Extraction...")
    json_result = ai_service.extract_text_from_image(image_data, format="json", provider="ollama")
    print("\n[JSON EXTRACTION]\n", json_result)

if __name__ == "__main__":
    asyncio.run(test_deepseek_ocr())
