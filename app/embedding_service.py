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
            "prompt": text
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=payload)
                if response.status_code != 200:
                    logger.error(f"Ollama embedding failed: {response.status_code} {response.text}")
                    return None
                
                data = response.json()
                return data.get("embedding")
                
            except Exception as e:
                logger.error(f"Error generating embedding: {e}")
                return None

    async def generate_batch_embeddings(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generates embeddings for a list of texts.
        Current Ollama API usually takes one prompt at a time, so we iterate efficiently.
        """
        results = []
        for text in texts:
            emb = await self.generate_embedding(text)
            results.append(emb)
        return results

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
