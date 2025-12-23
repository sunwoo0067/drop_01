
from app.normalization import clean_product_name
from app.services.ai.service import AIService
from app.db import SessionLocal
import asyncio

async def test_seo_enhancement():
    # 1. Test Cleaning
    test_names = [
        ("[무료배송] (관리-123) 삼성 삼성 UHD TV ★특가★", "삼성"),
        ("【본사직영】 나이키 에어맥스 (2023) - 화이트", "나이키"),
        ("로지텍 로지텍 마우스 G502", "로지텍")
    ]
    
    print("=== Cleaning Test ===")
    for original, brand in test_names:
        cleaned = clean_product_name(original, brand=brand)
        print(f"Original: {original} / Brand: {brand}")
        print(f"Cleaned:  {cleaned}\n")

    # 2. Test AI SEO Prompt Generation
    print("=== AI SEO Mock Test ===")
    ai = AIService()
    
    # Mock examples
    mock_examples = [
        {"original": "애플 아이폰 15", "processed": "애플 아이폰 15 128GB 자급제 블랙"},
        {"original": "소니 헤드폰 WH-1000XM5", "processed": "소니 WH-1000XM5 노이즈캔슬링 블루투스 헤드폰"}
    ]
    
    # Note: This will actually call the AI provider if keys are valid
    try:
        result = ai.optimize_seo(
            product_name="삼성 갤럭시 S24",
            keywords=["삼성", "스마트폰", "자급제"],
            benchmark_name="삼성전자 갤럭시 S24 256GB 울트라",
            category="가전/디지털",
            market="Coupang",
            examples=mock_examples
        )
        print(f"AI Result: {result}")
    except Exception as e:
        print(f"AI Service Call failed (Expected if no API keys): {e}")

if __name__ == "__main__":
    asyncio.run(test_seo_enhancement())
