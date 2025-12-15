import google.generativeai as genai
from app.settings import settings
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Configure Gemini
if settings.gemini_api_key:
    genai.configure(api_key=settings.gemini_api_key)
    # Using existing stable model
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    logger.warning("GEMINI_API_KEY is not set. AI features heavily restricted.")
    model = None

def extract_specs(text: str) -> Dict[str, Any]:
    """
    Extracts technical specifications from product description text/html.
    Returns a dictionary of key-value pairs (e.g. {"width": "50cm", "material": "aluminum"}).
    """
    if not model or not text:
        return {}

    prompt = f"""
    Extract technical specifications from the following product description.
    Return ONLY a valid JSON object where keys are spec names (normalized to snake_case if possible) and values are the values found.
    Focus on dimensions, material, weight, voltage, power, etc.
    Do not include generic marketing terms.
    
    Product Description:
    {text[:5000]}
    """
    
    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Error extracting specs: {e}")
        return {}

def analyze_pain_points(text: str) -> List[str]:
    """
    Analyzes product reviews or description to identify common user pain points or "cons".
    Returns a list of short strings (e.g. ["heavy", "installation difficult"]).
    """
    if not model or not text:
        return []

    prompt = f"""
    Analyze the following product text (which may contain reviews or honest descriptions) and identify potential NEGATIVE points or weaknesses (pain points).
    If it's just a description, infer what potential 'cons' might be based on the type of product (e.g. cheap plastic = breakage risk).
    Return ONLY a valid JSON list of strings.
    
    Text:
    {text[:5000]}
    """
    
    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Error analyzing pain points: {e}")
        return []

def optimize_seo(product_name: str, original_keywords: List[str]) -> Dict[str, Any]:
    """
    Optimizes product title and generates tags for SEO.
    Returns dict with 'title' and 'tags'.
    """
    if not model:
        return {"title": product_name, "tags": original_keywords[:20]}

    prompt = f"""
    Optimize the following product name for SEO on a Korean e-commerce platform (Coupang).
    Combine it with the provided keywords to make a rich, search-friendly title.
    Also select top 20 relevant tags.
    
    Original Name: {product_name}
    Related Keywords: {', '.join(original_keywords)}
    
    Rules:
    1. Title should be < 50 chars if possible, but descriptive. Main keywords first.
    2. Remove banned words like "Best", "No.1", "최고".
    3. Return JSON with keys: "title" (string), "tags" (list of strings).
    """
    
    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Error optimizing SEO: {e}")
        return {"title": product_name, "tags": original_keywords[:20]}

def predict_seasonality(product_name: str) -> Dict[str, Any]:
    """
    Predicts which months/seasons the product is most relevant for.
    Returns dict with 'score' (0.0-1.0 for CURRENT month) and 'months' (list of integers).
    """
    if not model:
        return {"score": 0.5, "months": []}

    import datetime
    current_month = datetime.datetime.now().month
    
    prompt = f"""
    Analyze the seasonality of the product: "{product_name}".
    Determine which months (1-12) this product is most popular.
    Also, give a relevance score (0.0 to 1.0) for the CURRENT month ({current_month}).
    
    Return JSON with keys:
    - "months": list of integers (e.g. [12, 1, 2] for winter items)
    - "current_month_score": float (relevance to now)
    """
    
    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Error predicting seasonality: {e}")
        return {"score": 0.5, "months": []} # Default neutral
