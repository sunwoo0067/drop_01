import httpx
import json
import logging
from typing import Dict, Any, List, Optional, Union, Literal
import base64
from app.services.ai.base import AIProvider

logger = logging.getLogger(__name__)

class OllamaProvider(AIProvider):
    def __init__(
        self, 
        base_url: str, 
        model_name: str, 
        function_model_name: Optional[str] = None, 
        reasoning_model_name: Optional[str] = None, 
        vision_model_name: Optional[str] = None,
        ocr_model_name: Optional[str] = None,
        qwen_vl_model_name: Optional[str] = None,
        logic_model_name: Optional[str] = None
    ):
        self.base_url = base_url
        self.model_name = model_name
        self.function_model_name = function_model_name or model_name
        self.reasoning_model_name = reasoning_model_name or model_name
        self.vision_model_name = vision_model_name or "drop-vision"
        self.ocr_model_name = ocr_model_name or "drop-ocr"
        self.qwen_vl_model_name = qwen_vl_model_name or "drop-qwen-vl"
        self.logic_model_name = logic_model_name or "granite4"
        logger.info(f"OllamaProvider initialized: main={model_name}, vision={self.vision_model_name}, logic={self.logic_model_name}")

    def _chat(
        self, 
        messages: List[Dict[str, str]], 
        model: str, 
        format: Optional[str] = None, 
        tools: Optional[List[Dict[str, Any]]] = None,
        images: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Internal method to call /api/chat endpoint.
        """
        url = f"{self.base_url}/api/chat"
        
        # In chat API, images are part of the message content
        # For simplicity, if images are provided, we attach them to the last message
        if images and messages:
            messages[-1]["images"] = images

        payload = {
            "model": model,
            "messages": messages,
            "stream": False
        }
        if format:
            payload["format"] = format
        if tools:
            payload["tools"] = tools

        try:
            with httpx.Client(timeout=300.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Ollama _chat failed (model={model}, format={format}): {e}")
            return {}

    def generate_text(self, prompt: str, model: Optional[str] = None) -> str:
        target_model = model or self.model_name
        messages = [{"role": "user", "content": prompt}]
        response = self._chat(messages, target_model)
        return response.get("message", {}).get("content", "")

    def generate_json(self, prompt: str, model: Optional[str] = None, tools: Optional[List[Dict[str, Any]]] = None, image_data: Optional[bytes] = None) -> Dict[str, Any] | List[Any]:
        target_model = model or (self.vision_model_name if image_data else self.function_model_name)
        messages = [{"role": "user", "content": prompt}]
        
        images = None
        if image_data:
            images = [base64.b64encode(image_data).decode("utf-8")]

        # If tools are provided, use Native Tool Calling
        if tools:
            response = self._chat(messages, target_model, tools=tools, images=images)
            message = response.get("message", {})
            if "tool_calls" in message:
                # Returns the first tool call's arguments as JSON
                try:
                    return message["tool_calls"][0].get("function", {}).get("arguments", {})
                except:
                    return {}
            # Fallback to content if no tool call
            content = message.get("content", "")
        else:
            # Use JSON mode with format="json"
            if "JSON" not in prompt:
                prompt += "\nReturn ONLY valid JSON."
            response = self._chat([{"role": "user", "content": prompt}], target_model, format="json", images=images)
            content = response.get("message", {}).get("content", "")

        try:
            if not content: return {}
            return json.loads(content)
        except Exception as e:
            logger.error(f"Failed to parse JSON for {target_model}: {e}")
            return {}

    def generate_reasoning(self, prompt: str, model: Optional[str] = None) -> str:
        target_model = model or self.reasoning_model_name
        messages = [
            {"role": "system", "content": "You are a logical reasoning expert. Break down the problem step-by-step."},
            {"role": "user", "content": prompt}
        ]
        response = self._chat(messages, target_model)
        return response.get("message", {}).get("content", "")

    def describe_image(self, image_data: bytes, prompt: str = "이 이미지를 상세히 설명해주세요.", model: Optional[str] = None) -> str:
        encoded_image = base64.b64encode(image_data).decode("utf-8")
        target_model = model or self.vision_model_name
        
        messages = [{"role": "user", "content": prompt}]
        response = self._chat(messages, target_model, images=[encoded_image])
        
        result = response.get("message", {}).get("content", "")
        
        # Fallback to llava if needed
        if not result and target_model != "llava":
            logger.info("Vision model failed. Retrying with llava fallback...")
            response = self._chat(messages, "llava", images=[encoded_image])
            result = response.get("message", {}).get("content", "")
            
        return result

    def extract_text_from_image(self, image_data: bytes, format: Literal["text", "markdown", "json"] = "text", model: Optional[str] = None) -> str:
        encoded_image = base64.b64encode(image_data).decode("utf-8")
        target_model = model or self.ocr_model_name
        
        # DeepSeek-OCR specific prompts
        if format == "markdown":
            prompt = "<|grounding|>Convert the document to markdown."
        elif format == "json":
            prompt = "Extract the text in the image and return as JSON."
        else:
            prompt = "Extract the text in the image."
            
        # Try /api/chat first
        messages = [{"role": "user", "content": prompt}]
        response = self._chat(messages, target_model, images=[encoded_image], format="json" if format == "json" else None)
        
        result = response.get("message", {}).get("content", "")
        
        # Fallback to /api/generate if /api/chat fails (happens with some specialized models)
        if not result:
            logger.info(f"Ollama chat failed for OCR. Trying /api/generate fallback...")
            url = f"{self.base_url}/api/generate"
            payload = {
                "model": target_model,
                "prompt": prompt,
                "stream": False,
                "images": [encoded_image]
            }
            if format == "json":
                payload["format"] = "json"
            try:
                with httpx.Client(timeout=300.0) as client:
                    resp = client.post(url, json=payload)
                    resp.raise_for_status()
                    result = resp.json().get("response", "")
            except Exception as e:
                logger.error(f"Ollama generate fallback failed: {e}")
                
        return result

    def analyze_visual_layout(self, image_data: bytes, prompt: str = "Analyze the visual layout and identify key elements with their positions.", model: Optional[str] = None) -> str:
        encoded_image = base64.b64encode(image_data).decode("utf-8")
        target_model = model or self.qwen_vl_model_name
        
        messages = [{"role": "user", "content": prompt}]
        response = self._chat(messages, target_model, images=[encoded_image])
        return response.get("message", {}).get("content", "")
