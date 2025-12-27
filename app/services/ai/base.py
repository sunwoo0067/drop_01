from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Literal

class AIProvider(ABC):
    @abstractmethod
    async def generate_text(self, prompt: str, model: Optional[str] = None) -> str:
        """
        Generates simple text response.
        """
        pass

    @abstractmethod
    async def generate_json(self, prompt: str, model: Optional[str] = None, image_data: Optional[bytes] = None) -> Dict[str, Any] | List[Any]:
        """
        Generates structured JSON response, optionally with image input.
        """
        pass

    @abstractmethod
    async def describe_image(self, image_data: bytes, prompt: str = "이 이미지를 상세히 설명해주세요. 특히 상품의 특징, 색상, 디자인, 재질 등을 중심으로 설명해주세요.", model: Optional[str] = None) -> str:
        """
        Describes the content of an image.
        """
        pass

    @abstractmethod
    async def generate_reasoning(self, prompt: str, model: Optional[str] = None) -> str:
        """
        Generates response using a reasoning-focused model.
        """
        pass

    @abstractmethod
    async def extract_text_from_image(self, image_data: bytes, format: Literal["text", "markdown", "json"] = "text", model: Optional[str] = None) -> str:
        """
        Extracts text from an image (OCR).
        """
        pass

    async def analyze_visual_layout(self, image_data: bytes, prompt: str = "Analyze visual layout.", model: Optional[str] = None) -> str:
        """
        Analyzes the visual layout and spatial information of an image.
        Default implementation falls back to describe_image.
        """
        return await self.describe_image(image_data, prompt=prompt, model=model)
