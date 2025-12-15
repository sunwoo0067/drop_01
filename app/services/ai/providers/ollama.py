import httpx
import json
import logging
from typing import Dict, Any, List, Optional
from app.services.ai.base import AIProvider

logger = logging.getLogger(__name__)

class OllamaProvider(AIProvider):
    def __init__(self, base_url: str = "http://localhost:11434", model_name: str = "gemma2"):
        self.base_url = base_url
        self.model_name = model_name

    def generate_text(self, prompt: str) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False
        }
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json().get("response", "")
        except Exception as e:
            logger.error(f"Ollama generate_text failed: {e}")
            return ""

    def generate_json(self, prompt: str) -> Dict[str, Any] | List[Any]:
        # Ollama's JSON mode is model dependent, often requires explicit prompt engineering + format=json
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt + "\nRespond in valid JSON.",
            "format": "json",
            "stream": False
        }
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                text = resp.json().get("response", "")
                return json.loads(text)
        except Exception as e:
            logger.error(f"Ollama generate_json failed: {e}")
            return {}
