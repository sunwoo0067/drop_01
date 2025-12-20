import google.generativeai as genai
import json
import logging
from typing import Dict, Any, List, Optional
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
from app.services.ai.base import AIProvider

logger = logging.getLogger(__name__)

class GeminiProvider(AIProvider):
    def __init__(self, api_keys: List[str], model_name: str = "gemini-1.5-flash-latest"):
        self.api_keys = [k for k in api_keys if k] # Filter empty
        self.model_name = model_name
        self.current_key_index = 0
        self._configure_current_key()

    def _configure_current_key(self):
        if not self.api_keys:
            logger.warning("No Gemini API Keys provided.")
            self.model = None
            return
        
        current_key = self.api_keys[self.current_key_index]
        genai.configure(api_key=current_key)
        self.model = genai.GenerativeModel(self.model_name)
        logger.info(f"Switched to Gemini Key Index: {self.current_key_index}")

    def _rotate_key(self) -> bool:
        """
        Rotates to the next available key.
        Returns True if rotation was successful (keys remaining), False otherwise.
        """
        if len(self.api_keys) <= 1:
            return False
            
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        self._configure_current_key()
        return True

    def generate_text(self, prompt: str) -> str:
        if not self.model:
            return ""

        max_retries = len(self.api_keys)
        attempts = 0

        while attempts < max_retries:
            try:
                response = self.model.generate_content(prompt)
                return response.text
            except (ResourceExhausted, ServiceUnavailable) as e:
                logger.warning(f"Gemini Key {self.current_key_index} exhausted/unavailable: {e}")
                if not self._rotate_key():
                    logger.error("All Gemini keys exhausted.")
                    return ""
                attempts += 1
            except Exception as e:
                logger.error(f"Gemini generate_text failed (non-retryable): {e}")
                return ""
        return ""

    def generate_json(self, prompt: str) -> Dict[str, Any] | List[Any]:
        if not self.model:
            return {}

        max_retries = len(self.api_keys)
        attempts = 0

        while attempts < max_retries:
            try:
                response = self.model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                return json.loads(response.text)
            except (ResourceExhausted, ServiceUnavailable) as e:
                logger.warning(f"Gemini Key {self.current_key_index} exhausted/unavailable: {e}")
                if not self._rotate_key():
                    logger.error("All Gemini keys exhausted.")
                    return {}
                attempts += 1
            except Exception as e:
                logger.error(f"Gemini generate_json failed (non-retryable): {e}")
                return {}
        return {}

    def describe_image(self, image_data: bytes, prompt: str = "이 이미지를 상세히 설명해주세요. 특히 상품의 특징, 색상, 디자인, 재질 등을 중심으로 설명해주세요.") -> str:
        if not self.model:
            return ""

        max_retries = len(self.api_keys)
        attempts = 0

        while attempts < max_retries:
            try:
                # Part for Gemini multimodal
                contents = [
                    prompt,
                    {"mime_type": "image/jpeg", "data": image_data}
                ]
                response = self.model.generate_content(contents)
                return response.text
            except (ResourceExhausted, ServiceUnavailable) as e:
                logger.warning(f"Gemini Key {self.current_key_index} exhausted/unavailable: {e}")
                if not self._rotate_key():
                    logger.error("All Gemini keys exhausted.")
                    return ""
                attempts += 1
            except Exception as e:
                logger.error(f"Gemini describe_image failed: {e}")
                return ""
        return ""
