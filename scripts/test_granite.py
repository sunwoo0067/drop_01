import sys
import os
import asyncio
import logging
import json

# Add app to path
sys.path.append(os.getcwd())

from app.services.ai.service import AIService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_granite_logic():
    ai_service = AIService()
    ollama = ai_service.ollama
    
    # 1. Data Cleaning & Transformation (Structured Data focus)
    logger.info("Test 1: Data Cleaning & JSON Transformation...")
    raw_data = """
    ITEM: Nike Air Zoom Pegasus 39
    PRICE: 129,000 KRW (Discount 10% available)
    STOCK: 15 units left
    SHIPPING: Within 2 days
    """
    prompt = f"Convert this raw product data into a structured JSON. Extract name, price_value, price_unit, discount_percent, stock_count, and shipping_days. Raw data: {raw_data}"
    
    # Use logic_model_name if initialized in provider
    target_model = getattr(ollama, "logic_model_name", "granite4")
    
    json_result = ollama.generate_json(prompt, model=target_model)
    print("\n[DATA TRANSFORMATION]\n", json.dumps(json_result, indent=2, ensure_ascii=False))

    # 2. Logic & Reasoning (Business Rule Enforcement)
    logger.info("Test 2: Business Logic Reasoning...")
    rules = """
    - If stock < 5, status is CRITICAL
    - If shipping_days > 3, status is DELAYED
    - Otherwise, status is NORMAL
    """
    data = {"stock_count": 3, "shipping_days": 2}
    prompt = f"Apply these rules: {rules} to this data: {data}. What is the status? Why?"
    
    logic_result = ollama.generate_text(prompt, model=target_model)
    print("\n[LOGIC REASONING]\n", logic_result)

    # 3. Multilingual Support (Korean -> English with explanation)
    logger.info("Test 3: Multilingual Analysis...")
    prompt = "이 상품의 '우주항공 등급 알루미늄'이라는 특징을 해외 사용자에게 매력적으로 번역하고 디자인적 가치를 설명해주세요."
    
    multi_result = ollama.generate_text(prompt, model=target_model)
    print("\n[MULTILINGUAL ANALYSIS]\n", multi_result)

if __name__ == "__main__":
    asyncio.run(test_granite_logic())
