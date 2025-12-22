import asyncio
import logging
import sys
import os

# 프로젝트 루트를 path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.embedding_service import EmbeddingService
from app.services.ai.service import AIService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_rich_rag():
    embedding_service = EmbeddingService()
    ai_service = AIService()
    
    test_text = "프리미엄 세라믹 식기 세트 4인용"
    # 테스트용 공개 이미지 URL (Unsplash 등)
    test_images = [
        "https://images.unsplash.com/photo-1574169208507-84376144848b?w=500&q=80"
    ]
    
    logger.info("--- 1. Testing describe_image directly ---")
    import httpx
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(test_images[0])
            if resp.status_code == 200:
                # AIService.describe_image is synchronous, but Ollama/Gemini internally use httpx.Client
                # In a real app, you might want to wrap this in run_in_executor if it blocks too long.
                description = ai_service.describe_image(resp.content)
                logger.info(f"Generated Description: {description}")
            else:
                logger.error(f"Failed to download test image: {resp.status_code}")
        except Exception as e:
            logger.error(f"Error in direct description test: {e}")

    logger.info("\n--- 2. Testing generate_rich_embedding ---")
    try:
        rich_emb = await embedding_service.generate_rich_embedding(test_text, image_urls=test_images)
        if rich_emb:
            logger.info(f"Rich Embedding generated successfully! Dimension: {len(rich_emb)}")
            logger.info(f"First 5 values: {rich_emb[:5]}")
        else:
            logger.error("Rich Embedding generation returned None.")
    except Exception as e:
        logger.error(f"Error in rich embedding generation: {e}")

if __name__ == "__main__":
    asyncio.run(test_rich_rag())
