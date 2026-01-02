from app.db import SessionLocal
from app.services.analytics.coupang_policy import CoupangSourcingPolicyService
import json

def test_keyword_eval():
    session = SessionLocal()
    try:
        # 1. 기존 데이터가 있는 키워드 (가정)
        # 만약 DB에 데이터가 없다면 RESEARCH가 나오겠지만, 
        # 로직상 Accelerated Learning이 작동하는지 확인
        keywords = ["가습기", "아이패드", "커피"]
        
        for kw in keywords:
            print(f"\n--- Evaluating Keyword: {kw} ---")
            result = CoupangSourcingPolicyService.evaluate_keyword_policy(session, kw)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
    finally:
        session.close()

if __name__ == "__main__":
    test_keyword_eval()
