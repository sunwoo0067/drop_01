import asyncio
import logging
from app.services.ai import AIService

async def test():
    print("Initializing AIService...")
    s = AIService()
    print("Generating JSON with provider='auto'...")
    try:
        r = await s.generate_json('고객 문의: "배송 언제와요?" 이 내용을 분석해서 {"intent": "배송문의"} 형식으로 응답하세요.', provider='auto')
        print(f"Result: {r}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
