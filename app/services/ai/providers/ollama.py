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

    def describe_image(self, image_data: bytes, prompt: str = "이 이미지를 상세히 설명해주세요. 특히 상품의 특징, 색상, 디자인, 재질 등을 중심으로 설명해주세요.") -> str:
        import base64
        url = f"{self.base_url}/api/generate"
        
        # Use a multimodal model if possible, fallback to current model
        # Ollama usually needs 'llava' or similar for images.
        model = "llava" if "llava" in self.model_name else self.model_name
        
        encoded_image = base64.b64encode(image_data).decode("utf-8")
        payload = {
            "model": model,
            "prompt": prompt,
            "images": [encoded_image],
            "stream": False
        }
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json().get("response", "")
        except Exception as e:
            logger.error(f"Ollama describe_image failed: {e}")
            return ""
