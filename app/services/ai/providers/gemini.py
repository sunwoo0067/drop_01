import google.generativeai as genai
import json
import logging
from typing import Dict, Any, List, Optional, Literal
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
from app.services.ai.base import AIProvider

logger = logging.getLogger(__name__)

class GeminiProvider(AIProvider):
    def __init__(self, api_keys: List[str], model_name: str = "gemini-1.5-flash"):
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

    def generate_text(self, prompt: str, model: Optional[str] = None) -> str:
        if not self.model:
            return ""

        target_model_name = model or self.model_name
        # If model is different from the current one, we might need to reconfigure
        # but for simplicity in this PoC, we assume use of self.model if model is None
        # OR we could dynamically create a model instance if needed.
        # Here we'll implement a simple dynamic switch.
        
        target_model = self.model
        if model and model != self.model_name:
             target_model = genai.GenerativeModel(model)

        max_retries = len(self.api_keys)
        attempts = 0

        while attempts < max_retries:
            try:
                response = target_model.generate_content(prompt)
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

    def generate_json(self, prompt: str, model: Optional[str] = None) -> Dict[str, Any] | List[Any]:
        if not self.model:
            return {}

        target_model = self.model
        if model and model != self.model_name:
             target_model = genai.GenerativeModel(model)

        max_retries = len(self.api_keys)
        attempts = 0

        while attempts < max_retries:
            try:
                response = target_model.generate_content(
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
    def describe_image(self, image_data: bytes, prompt: str = "이 이미지를 상세히 설명해주세요.", model: Optional[str] = None) -> str:
        return self._generate_with_image(image_data, prompt, model)

    def extract_text_from_image(self, image_data: bytes, format: Literal["text", "markdown", "json"] = "text", model: Optional[str] = None) -> str:
        prompt = f"Extract all text from this image. Output format: {format}."
        return self._generate_with_image(image_data, prompt, model)

    def _generate_with_image(self, image_data: bytes, prompt: str, model: Optional[str] = None) -> str:
        if not self.model:
            return ""

        target_model_name = model or self.model_name
        target_model = self.model
        if model and model != self.model_name:
             target_model = genai.GenerativeModel(model)

        max_retries = len(self.api_keys)
        attempts = 0

        while attempts < max_retries:
            try:
                response = target_model.generate_content([prompt, {"mime_type": "image/jpeg", "data": image_data}])
                return response.text
            except (ResourceExhausted, ServiceUnavailable) as e:
                logger.warning(f"Gemini Key {self.current_key_index} exhausted/unavailable: {e}")
                if not self._rotate_key():
                    return ""
                attempts += 1
            except Exception as e:
                logger.error(f"Gemini image generation failed: {e}")
                return ""
        return ""

    def generate_reasoning(self, prompt: str, model: Optional[str] = None) -> str:
        # Standard Gemini models handle reasoning well within normal chat.
        return self.generate_text(prompt, model=model)

    def analyze_visual_layout(self, image_data: bytes, prompt: str = "Analyze the visual layout and identify key elements with their positions.", model: Optional[str] = None) -> str:
        prompt += " Please provide spatial coordinates or describe the layout in detail."
        return self._generate_with_image(image_data, prompt, model)
