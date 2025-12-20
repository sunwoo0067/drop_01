import logging
import httpx
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "nomic-embed-text"):
        self.base_url = base_url
        self.model = model

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generates embedding for the given text using Ollama.
        """
        if not text:
            return None

        url = f"{self.base_url}/api/embeddings"
        payload = {
            "model": self.model,
            "prompt": text,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=payload)
                if response.status_code != 200:
                    logger.error("Ollama embedding failed: %s %s", response.status_code, response.text)
                    return None

                data = response.json()
                return data.get("embedding")

            except Exception as exc:
                logger.error("Error generating embedding: %s", exc)
                return None

    async def generate_batch_embeddings(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generates embeddings for a list of texts.
        Current Ollama API usually takes one prompt at a time, so we iterate efficiently.
        """
        results: List[Optional[List[float]]] = []
        for text in texts:
            emb = await self.generate_embedding(text)
            results.append(emb)
        return results

    async def generate_rich_embedding(
        self,
        text: str,
        image_urls: Optional[List[str]] = None,
        max_images: int = 3,
    ) -> Optional[List[float]]:
        """
        Generates a rich embedding by combining text with image descriptions.
        """
        if not text and not image_urls:
            return None

        combined_text = (text or "").strip()

        if image_urls:
            from app.services.ai.service import AIService  # Lazy import to avoid circular dependency

            ai_service = AIService()
            image_descriptions: List[str] = []
            async with httpx.AsyncClient(timeout=30.0) as client:
                for url in image_urls[:max_images]:
                    try:
                        resp = await client.get(url)
                        if resp.status_code != 200:
                            continue
                        description = ai_service.describe_image(resp.content)
                        if description:
                            image_descriptions.append(f"[Image Description: {description}]")
                    except Exception as exc:
                        logger.error("Error describing image for rich embedding (%s): %s", url, exc)

            if image_descriptions:
                combined_text = f"{combined_text}\n" + "\n".join(image_descriptions)

        # 원본 텍스트 + 이미지 캡션을 합쳐서 임베딩 생성 (최대 4000자 제한)
        return await self.generate_embedding(combined_text[:4000])

    def compute_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Simple cosine similarity implementation if needed on-the-fly.
        Ideally use pgvector's <-> operator in DB.
        """
        import numpy as np
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        if np.linalg.norm(v1) == 0 or np.linalg.norm(v2) == 0:
            return 0.0
        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
