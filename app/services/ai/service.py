import logging
from typing import Dict, Any, List, Literal, Optional

from app.settings import settings
from app.db import SessionLocal
from app.models import APIKey
from app.services.ai.base import AIProvider
from app.services.ai.providers.gemini import GeminiProvider
from app.services.ai.providers.ollama import OllamaProvider
from app.services.ai.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)

ProviderType = Literal["gemini", "ollama", "openai", "auto"]

class AIService:
    def __init__(self):
        # 1. Fetch DB Keys
        db_gemini_keys = self._get_db_keys("gemini")
        db_openai_keys = self._get_db_keys("openai")

        # 2. Setup Gemini Keys (Env + DB)
        gemini_keys = settings.gemini_api_keys.copy()
        if settings.gemini_api_key and settings.gemini_api_key not in gemini_keys:
             gemini_keys.insert(0, settings.gemini_api_key)
        gemini_keys.extend([k for k in db_gemini_keys if k not in gemini_keys])
        
        # 3. Setup OpenAI Keys (Env + DB)
        openai_keys = settings.openai_api_keys.copy()
        openai_keys.extend([k for k in db_openai_keys if k not in openai_keys])

        self.gemini = GeminiProvider(api_keys=gemini_keys)
        self.ollama = OllamaProvider(
            base_url=settings.ollama_base_url, 
            model_name=settings.ollama_model,
            function_model_name=settings.ollama_function_model,
            reasoning_model_name=settings.ollama_reasoning_model,
            vision_model_name=settings.ollama_vision_model,
            ocr_model_name=settings.ollama_ocr_model,
            qwen_vl_model_name=settings.ollama_qwen_vl_model,
            logic_model_name=settings.ollama_logic_model
        )
        self.openai = OpenAIProvider(api_keys=openai_keys, model_name=settings.openai_model)
        
        self.default_provider_name = settings.default_ai_provider

    def _get_db_keys(self, provider: str) -> List[str]:
        try:
            with SessionLocal() as db:
                keys = db.query(APIKey.key).filter(
                    APIKey.provider == provider, 
                    APIKey.is_active == True
                ).all()
                return [k[0] for k in keys]
        except Exception as e:
            logger.error(f"Failed to fetch {provider} keys from DB: {e}")
            return []

    def _get_provider(self, provider_type: ProviderType = "auto") -> AIProvider:
        if provider_type == "auto":
            provider_type = self.default_provider_name
        
        if provider_type == "gemini":
            return self.gemini
        elif provider_type == "ollama":
            return self.ollama
        elif provider_type == "openai":
            return self.openai
        else:
            return self.openai

    def extract_specs(self, text: str, provider: ProviderType = "auto") -> Dict[str, Any]:
        text_len = len(text)
        is_ollama = provider == "ollama" or (provider == "auto" and self.default_provider_name == "ollama")
        target_provider = self._get_provider(provider)
        target_model = None
        
        # Default to logic model for Ollama extraction tasks
        if is_ollama:
            target_model = settings.ollama_logic_model
            
        # If text is long and using Ollama, use the long-context capable model (Ministral 3B)
        if is_ollama and text_len > 4000:
            logger.info(f"Long text detected ({text_len} chars). Overriding with {settings.ollama_vision_model}")
            target_model = settings.ollama_vision_model

        prompt = f"""
        Extract technical specifications from the following product description.
        Return ONLY a valid JSON object where keys are spec names (normalized to snake_case if possible) and values are the values found.
        Focus on dimensions, material, weight, voltage, power, etc.
        
        Text: {text[:100000]}
        """
        return target_provider.generate_json(prompt, model=target_model)

    def analyze_pain_points(self, text: str, provider: ProviderType = "auto") -> List[str]:
        text_len = len(text)
        is_ollama = provider == "ollama" or (provider == "auto" and self.default_provider_name == "ollama")
        
        target_provider = self._get_provider(provider)
        target_model = None
        
        # Default to logic model for Ollama analysis tasks
        if is_ollama:
            target_model = settings.ollama_logic_model
            
        if is_ollama and text_len > 4000:
            logger.info(f"Long text detected ({text_len} chars). Overriding with {settings.ollama_vision_model}")
            target_model = settings.ollama_vision_model

        prompt = f"""
        Analyze the following text and identify potential NEGATIVE points or weaknesses (pain points).
        Return ONLY a list of strings in JSON format.
        
        Text: {text[:100000]}
        """
        result = target_provider.generate_json(prompt, model=target_model)
        if isinstance(result, list):
            return result
        return []

    def optimize_seo(self, product_name: str, keywords: List[str], context: Optional[str] = None, provider: ProviderType = "auto") -> Dict[str, Any]:
        clean_keywords = [str(k) for k in keywords if k]
        target_provider = self._get_provider(provider)
        
        # Use logic model for SEO optimization if using Ollama
        target_model = None
        if provider == "ollama" or (provider == "auto" and self.default_provider_name == "ollama"):
            target_model = settings.ollama_logic_model
            
        context_str = f"\nContext/Details: {context[:5000]}" if context else ""
        
        prompt = f"""
        Optimize product name for SEO (Coupang).
        Original Name: {product_name}
        Keywords: {', '.join(clean_keywords)}{context_str}
        
        Instructions:
        1. Create a professional and searchable product title.
        2. Extract or refine relevant tags/keywords.
        3. Use the provided context (description/OCR) to ensure accuracy.
        
        Return JSON {{ "title": "...", "tags": [...] }}
        """
        return target_provider.generate_json(prompt, model=target_model)

    def predict_seasonality(self, product_name: str, provider: ProviderType = "auto") -> Dict[str, Any]:
        import datetime
        current_month = datetime.datetime.now().month
        target_provider = self._get_provider(provider)
        
        # Use logic model for seasonality prediction if using Ollama
        target_model = None
        if provider == "ollama" or (provider == "auto" and self.default_provider_name == "ollama"):
            target_model = settings.ollama_logic_model
            
        prompt = f"""
        Analyze seasonality for "{product_name}".
        Return JSON {{ "months": [int], "current_month_score": float (relevance to month {current_month}) }}
        """
        return target_provider.generate_json(prompt, model=target_model)

    def generate_json(self, prompt: str, model: Optional[str] = None, provider: ProviderType = "auto") -> Dict[str, Any]:
        """Generic JSON generation method for agents"""
        target_provider = self._get_provider(provider)
        
        # Default to logic model for general JSON tasks if using Ollama and no specific model provided
        if not model and (provider == "ollama" or (provider == "auto" and self.default_provider_name == "ollama")):
            model = settings.ollama_logic_model
            
        return target_provider.generate_json(prompt, model=model)

    def describe_image(self, image_data: bytes, prompt: str = "이 이미지를 상세히 설명해주세요. 특히 상품의 특징, 색상, 디자인, 재질 등을 중심으로 설명해주세요.", provider: ProviderType = "auto") -> str:
        return self._get_provider(provider).describe_image(image_data, prompt)

    def extract_text_from_image(self, image_data: bytes, format: Literal["text", "markdown", "json"] = "text", provider: ProviderType = "auto") -> str:
        return self._get_provider(provider).extract_text_from_image(image_data, format=format)

    def analyze_visual_layout(self, image_data: bytes, prompt: str = "이 이미지의 시각적 레이아웃을 분석하고 주요 요소들의 위치를 파악해주세요.", provider: ProviderType = "auto") -> str:
        provider_obj = self._get_provider(provider)
        if hasattr(provider_obj, "analyze_visual_layout"):
            return provider_obj.analyze_visual_layout(image_data, prompt=prompt)
        return provider_obj.describe_image(image_data, prompt=prompt)

    def suggest_sourcing_strategy(self, market_trends: str, existing_products: List[str], provider: ProviderType = "auto") -> str:
        target_provider = self._get_provider(provider)
        
        # Use logic model for strategy reasoning if using Ollama
        target_model = None
        if provider == "ollama" or (provider == "auto" and self.default_provider_name == "ollama"):
            target_model = settings.ollama_logic_model
            
        prompt = f"""
        Market Trends: {market_trends[:2000]}
        Existing Products: {', '.join(existing_products[:50])}
        
        Based on the above information, suggest a detailed dropshipping sourcing strategy.
        Think step-by-step about:
        1. Potential niche markets.
        2. High-demand keyword clusters.
        3. Gap analysis (what's missing?).
        4. Predicted seasonality and timing.
        
        Provide a comprehensive strategy report.
        """
        return target_provider.generate_reasoning(prompt, model=target_model)
