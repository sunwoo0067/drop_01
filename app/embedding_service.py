import logging
import httpx
from typing import List, Optional

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
