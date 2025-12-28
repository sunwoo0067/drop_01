import httpx
import json
import logging
import base64
from typing import Dict, Any, List, Optional, Literal
from app.services.ai.base import AIProvider

logger = logging.getLogger(__name__)

class StableDiffusionProvider(AIProvider):
    """
    Stable Diffusion (Automatic1111 / Forge / etc.) API Provider
    """
    def __init__(self, base_url: str, model_name: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    async def generate_text(self, prompt: str, model: Optional[str] = None) -> str:
        # SD is not for text generation
        raise NotImplementedError("StableDiffusionProvider does not support generate_text")

    async def generate_json(self, prompt: str, model: Optional[str] = None, image_data: Optional[bytes] = None) -> Dict[str, Any] | List[Any]:
        # SD is not for JSON generation
        raise NotImplementedError("StableDiffusionProvider does not support generate_json")

    async def describe_image(self, image_data: bytes, prompt: str = "", model: Optional[str] = None) -> str:
        # Some SD setups support Interrogator (CLIP/DeepDanbooru)
        url = f"{self.base_url}/sdapi/v1/interrogate"
        payload = {
            "image": base64.b64encode(image_data).decode("utf-8"),
            "model": "clip"
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json().get("caption", "")
        except Exception as e:
            logger.error(f"SD describe_image failed: {e}")
            return ""

    async def generate_reasoning(self, prompt: str, model: Optional[str] = None) -> str:
        raise NotImplementedError("StableDiffusionProvider does not support generate_reasoning")

    async def extract_text_from_image(self, image_data: bytes, format: Literal["text", "markdown", "json"] = "text", model: Optional[str] = None) -> str:
        raise NotImplementedError("StableDiffusionProvider does not support extract_text_from_image")

    async def generate_image(self, prompt: str, negative_prompt: str = "", width: int = 1024, height: int = 1024, model: Optional[str] = None) -> bytes:
        """
        Calls /sdapi/v1/txt2img (or img2img in the future)
        """
        url = f"{self.base_url}/sdapi/v1/txt2img"
        
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "steps": 25,
            "width": width,
            "height": height,
            "cfg_scale": 7,
            "sampler_name": "Euler a",
            "override_settings": {
                "sd_model_checkpoint": model or self.model_name
            } if (model or self.model_name) else {}
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                images = data.get("images", [])
                if images:
                    return base64.b64decode(images[0])
            return b""
        except Exception as e:
            logger.error(f"SD generate_image failed: {e}")
            return b""
