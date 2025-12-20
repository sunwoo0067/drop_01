import logging
from typing import Dict, Any, List, Literal

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
        self.ollama = OllamaProvider(base_url=settings.ollama_base_url, model_name=settings.ollama_model)
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
        
        self.default_provider_name = settings.default_ai_provider

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
            # Fallback based on default, or hard fallback to openai?
            # If default is auto and name was unknown, fallback to openai
            return self.openai

    def extract_specs(self, text: str, provider: ProviderType = "auto") -> Dict[str, Any]:
        prompt = f"""
        Extract technical specifications from the following product description.
        Return ONLY a valid JSON object where keys are spec names (normalized to snake_case if possible) and values are the values found.
        Focus on dimensions, material, weight, voltage, power, etc.
        
        Text: {text[:4000]}
        """
        return self._get_provider(provider).generate_json(prompt)

    def analyze_pain_points(self, text: str, provider: ProviderType = "auto") -> List[str]:
        prompt = f"""
        Analyze the following text and identify potential NEGATIVE points or weaknesses (pain points).
        Return ONLY a list of strings in JSON format.
        
        Text: {text[:4000]}
        """
        result = self._get_provider(provider).generate_json(prompt)
        if isinstance(result, list):
            return result
        return []

    def optimize_seo(self, product_name: str, keywords: List[str], provider: ProviderType = "auto") -> Dict[str, Any]:
        prompt = f"""
        Optimize product name for SEO (Coupang).
        Original: {product_name}
        Keywords: {', '.join(keywords)}
        Return JSON {{ "title": "...", "tags": [...] }}
        """
        return self._get_provider(provider).generate_json(prompt)

    def predict_seasonality(self, product_name: str, provider: ProviderType = "auto") -> Dict[str, Any]:
        import datetime
        current_month = datetime.datetime.now().month
        prompt = f"""
        Analyze seasonality for "{product_name}".
        Return JSON {{ "months": [int], "current_month_score": float (relevance to month {current_month}) }}
        """
        return self._get_provider(provider).generate_json(prompt)

    def describe_image(self, image_data: bytes, prompt: str = "이 이미지를 상세히 설명해주세요. 특히 상품의 특징, 색상, 디자인, 재질 등을 중심으로 설명해주세요.", provider: ProviderType = "auto") -> str:
        """
        Describes the content of an image using the selected provider.
        """
        return self._get_provider(provider).describe_image(image_data, prompt)
