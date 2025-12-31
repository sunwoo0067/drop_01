import asyncio
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.append(os.getcwd())

from app.services.ai.agents.automation_policy import policy_engine

async def verify_policy():
    print("=== [v1.7.1] Automation Policy Verification ===\n")
    
    test_cases = [
        {
            "name": "Low Risk: Delivery Inquiry (High Confidence)",
            "state": {
                "confidence_score": 0.95,
                "intent": "배송조회",
                "product_info": {"category": "생활잡화"},
                "raw_content": "내 물건 어디쯤 왔나요?"
            }
        },
        {
            "name": "Medium Risk: Option Change (Medium Confidence)",
            "state": {
                "confidence_score": 0.88,
                "intent": "옵션변경",
                "product_info": {"category": "생활가전"},
                "raw_content": "색상 변경 가능한가요?"
            }
        },
        {
            "name": "High Risk: Return Request (High Confidence)",
            "state": {
                "confidence_score": 0.98,
                "intent": "반품요청",
                "product_info": {"category": "생활잡화"},
                "raw_content": "맘에 안들어서 반품하고 싶어요."
            }
        },
        {
            "name": "Critical Risk: Medical Device (High Confidence)",
            "state": {
                "confidence_score": 0.95,
                "intent": "사용법",
                "product_info": {"category": "의료기기"},
                "raw_content": "이 혈압계 어떻게 사용하나요?"
            }
        },
        {
            "name": "Critical Risk: Legal Keyword",
            "state": {
                "confidence_score": 0.99,
                "intent": "배송문의",
                "product_info": {"category": "생활잡화"},
                "raw_content": "내일까지 안오면 소비자원 신고하겠습니다."
            }
        }
    ]
    
    for case in test_cases:
        print(f"Testing: {case['name']}")
        can_automate, reason, meta = policy_engine.evaluate(case['state'])
        
        status = "✅ [AUTO_APPROVED]" if can_automate else "❌ [HUMAN_REVIEW]"
        print(f"Status: {status}")
        print(f"Reason: {reason}")
        print(f"Details: {meta}")
        print("-" * 40)

if __name__ == "__main__":
    asyncio.run(verify_policy())
