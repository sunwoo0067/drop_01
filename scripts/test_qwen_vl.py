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

async def test_qwen_vl():
    ai_service = AIService()
    
    # Sample image with multiple objects
    image_url = "https://images.unsplash.com/photo-1542291026-7eec264c27ff" # Nike Shoe
    
    try:
        logger.info(f"Downloading sample image for Qwen-VL: {image_url}")
        response = requests.get(image_url, timeout=10)
        image_data = response.content
    except Exception as e:
        logger.error(f"Failed to download image: {e}")
        return

    # 1. General Visual Analysis (Describe)
    logger.info("Test 1: General Visual Analysis...")
    desc_result = ai_service.describe_image(image_data, prompt="Describe what you see in this image in detail.", provider="ollama")
    print("\n[GENERAL ANALYSIS]\n", desc_result)

    # 2. Visual Layout & Grounding
    logger.info("Test 2: Visual Layout & Grounding...")
    # Requesting specific bounding boxes
    prompt = "Find the nike logo and the shoe. Return the bounding boxes in [[ymin, xmin, ymax, xmax]] format."
    layout_result = ai_service.analyze_visual_layout(image_data, prompt=prompt, provider="ollama")
    print("\n[VISUAL LAYOUT & GROUNDING]\n", layout_result)

    # 3. Text & Layout Interaction
    logger.info("Test 3: Complex Reasoning...")
    prompt = "What is the brand of this shoe and where is the logo located?"
    reason_result = ai_service.describe_image(image_data, prompt=prompt, provider="ollama")
    print("\n[COMPLEX REASONING]\n", reason_result)

if __name__ == "__main__":
    asyncio.run(test_qwen_vl())
