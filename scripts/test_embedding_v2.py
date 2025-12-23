import sys
import os
import asyncio
import logging

# Add app to path
sys.path.append(os.getcwd())

from app.embedding_service import EmbeddingService
from app.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_embedding_v2():
    logger.info(f"Checking embedding model: {settings.ollama_embedding_model}")
    service = EmbeddingService()
    
    test_text = "안녕하세요. 고해상도 다이나믹 드라이버가 탑재된 무선 헤드폰입니다."
    
    logger.info("Generating embedding...")
    embedding = await service.generate_embedding(test_text)
    
    if embedding:
        logger.info(f"✅ Success: Embedding generated. Length: {len(embedding)}")
        if len(embedding) == 768:
            logger.info("✅ Success: Dimension matches project requirement (768).")
        else:
            logger.warning(f"⚠️ Warning: Dimension mismatch! Expected 768, got {len(embedding)}")
            
        # 간단한 유사도 테스트
        test_text_2 = "노이즈 캔슬링 기능이 있는 무선 헤드폰"
        emb2 = await service.generate_embedding(test_text_2)
        if emb2:
            similarity = service.compute_similarity(embedding, emb2)
            logger.info(f"Similarity between similar texts: {similarity:.4f}")
            
    else:
        logger.error("❌ Failed: Embedding generation returned None.")

if __name__ == "__main__":
    asyncio.run(test_embedding_v2())
