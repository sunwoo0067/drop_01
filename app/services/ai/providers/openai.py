import logging
import json
from typing import Dict, Any, List, Optional, Literal
import openai
from openai import AsyncOpenAI, RateLimitError, AuthenticationError, APIConnectionError
from app.services.ai.base import AIProvider

logger = logging.getLogger(__name__)

class OpenAIProvider(AIProvider):
    def __init__(self, api_keys: List[str], model_name: str = "gpt-4o-mini"):
        self.api_keys = [k for k in api_keys if k]
        self.model_name = model_name
        self.current_key_index = 0
        self.client: Optional[AsyncOpenAI] = None
        self._configure_current_key()

    def _configure_current_key(self):
        if not self.api_keys:
            logger.warning("No OpenAI API Keys provided.")
            self.client = None
            return
        
        current_key = self.api_keys[self.current_key_index]
        self.client = AsyncOpenAI(api_key=current_key)
        logger.info(f"Switched to OpenAI Key Index: {self.current_key_index}")

    def _rotate_key(self) -> bool:
        if len(self.api_keys) <= 1:
            return False
        
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        self._configure_current_key()
        return True

    async def generate_text(self, prompt: str, model: Optional[str] = None) -> str:
        if not self.client:
            return ""

        target_model = model or self.model_name
        max_retries = len(self.api_keys)
        attempts = 0

        while attempts < max_retries:
            try:
                response = await self.client.chat.completions.create(
                    model=target_model,
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

    async def generate_json(self, prompt: str, model: Optional[str] = None, image_data: Optional[bytes] = None) -> Dict[str, Any] | List[Any]:
        if not self.client:
            return {}

        target_model = model or self.model_name
        max_retries = len(self.api_keys)
        attempts = 0

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": "You are a helpful assistant. Output valid JSON only."}
        ]

        if image_data:
            import base64
            encoded_image = base64.b64encode(image_data).decode("utf-8")
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"},
                    },
                ],
            })
        else:
            messages.append({"role": "user", "content": prompt})

        while attempts < max_retries:
            try:
                response = await self.client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.3
                )
                content = response.choices[0].message.content
                if not content: return {}
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

    async def describe_image(self, image_data: bytes, prompt: str = "이 이미지를 상세히 설명해주세요. 특히 상품의 특징, 색상, 디자인, 재질 등을 중심으로 설명해주세요.", model: Optional[str] = None) -> str:
        return await self._generate_with_image(image_data, prompt, model)

    async def extract_text_from_image(self, image_data: bytes, format: Literal["text", "markdown", "json"] = "text", model: Optional[str] = None) -> str:
        prompt = f"Extract all text from this image. Output format: {format}."
        if format == "json":
            prompt += " Return ONLY valid JSON."
        return await self._generate_with_image(image_data, prompt, model)

    async def _generate_with_image(self, image_data: bytes, prompt: str, model: Optional[str] = None) -> str:
        if not self.client:
            return ""

        import base64
        target_model = model or self.model_name
        encoded_image = base64.b64encode(image_data).decode("utf-8")
        
        max_retries = len(self.api_keys)
        attempts = 0

        while attempts < max_retries:
            try:
                response = await self.client.chat.completions.create(
                    model=target_model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"},
                                },
                            ],
                        }
                    ],
                    max_tokens=1000
                )
                return response.choices[0].message.content or ""
            except (RateLimitError, AuthenticationError, APIConnectionError) as e:
                logger.warning(f"OpenAI Image generation error: {e}. Rotating keys.")
                if not self._rotate_key():
                    return ""
                attempts += 1
            except Exception as e:
                logger.error(f"OpenAI image generation failed: {e}")
                return ""
        return ""

    async def generate_reasoning(self, prompt: str, model: Optional[str] = None) -> str:
        # Specific reasoning models (like o1) might require different configs, but for now reuse text
        return await self.generate_text(prompt, model=model)

    async def analyze_visual_layout(self, image_data: bytes, prompt: str = "Analyze the visual layout and identify key elements with their positions.", model: Optional[str] = None) -> str:
        prompt += " Please provide spatial coordinates or describe the layout in detail."
        return await self._generate_with_image(image_data, prompt, model)
