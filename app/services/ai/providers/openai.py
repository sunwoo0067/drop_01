import logging
import json
from typing import Dict, Any, List, Optional
import openai
from openai import OpenAI, RateLimitError, AuthenticationError, APIConnectionError
from app.services.ai.base import AIProvider

logger = logging.getLogger(__name__)

class OpenAIProvider(AIProvider):
    def __init__(self, api_keys: List[str], model_name: str = "gpt-4o-mini"):
        self.api_keys = [k for k in api_keys if k]
        self.model_name = model_name
        self.current_key_index = 0
        self.client: Optional[OpenAI] = None
        self._configure_current_key()

    def _configure_current_key(self):
        if not self.api_keys:
            logger.warning("No OpenAI API Keys provided.")
            self.client = None
            return
        
        current_key = self.api_keys[self.current_key_index]
        self.client = OpenAI(api_key=current_key)
        logger.info(f"Switched to OpenAI Key Index: {self.current_key_index}")

    def _rotate_key(self) -> bool:
        if len(self.api_keys) <= 1:
            return False
        
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        self._configure_current_key()
        return True

    def generate_text(self, prompt: str) -> str:
        if not self.client:
            return ""

        max_retries = len(self.api_keys)
        attempts = 0

        while attempts < max_retries:
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7
                )
                return response.choices[0].message.content or ""
            except (RateLimitError, AuthenticationError, APIConnectionError) as e:
                logger.warning(f"OpenAI Key {self.current_key_index} error: {e}. Rotating.")
                if not self._rotate_key():
                    logger.error("All OpenAI keys exhausted.")
                    return ""
                attempts += 1
            except Exception as e:
                logger.error(f"OpenAI generate_text failed: {e}")
                return ""
        return ""

    def generate_json(self, prompt: str) -> Dict[str, Any] | List[Any]:
        if not self.client:
            return {}

        max_retries = len(self.api_keys)
        attempts = 0

        while attempts < max_retries:
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant. Output valid JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3
                )
                content = response.choices[0].message.content
                return json.loads(content)
            except (RateLimitError, AuthenticationError, APIConnectionError) as e:
                logger.warning(f"OpenAI Key {self.current_key_index} error: {e}. Rotating.")
                if not self._rotate_key():
                    logger.error("All OpenAI keys exhausted.")
                    return {}
                attempts += 1
            except Exception as e:
                logger.error(f"OpenAI generate_json failed: {e}")
                return {}
        return {}
