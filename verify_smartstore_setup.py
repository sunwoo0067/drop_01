import uuid
from app.db import SessionLocal
from app.models import MarketAccount
from app.api.endpoints.settings import create_smartstore_account, SmartStoreAccountIn, list_smartstore_accounts
from pydantic import BaseModel

def verify_smartstore_setup():
    db = SessionLocal()
    try:
        print("\n" + "="*50)
        print("Verifying SmartStore Account Setup")
        print("="*50)
        
        # 1. 기존 테스트 데이터 삭제 (Clean up)
        db.query(MarketAccount).filter(MarketAccount.market_code == "SMARTSTORE").delete()
        db.commit()
        
        # 2. 계정 생성 테스트
        test_payload = SmartStoreAccountIn(
            name="Test Naver Account",
            client_id="NAVER_CLIENT_ID_123456",
            client_secret="NAVER_SECRET_7890",
            is_active=True
        )
        
        print(f"Creating test account: {test_payload.name}")
        result = create_smartstore_account(test_payload, db)
        print(f"Created Account ID: {result['id']}")
        print(f"Masked Client ID: {result['clientIdMasked']}")
        
        # 3. 목록 조회 테스트
        print("\nListing SmartStore accounts...")
        accounts = list_smartstore_accounts(db)
        print(f"Total SmartStore accounts: {len(accounts)}")
        for acc in accounts:
            print(f"- {acc['name']} (Active: {acc['isActive']})")
        
        if len(accounts) > 0 and accounts[0]['name'] == test_payload.name:
            print("\nSUCCESS: SmartStore account management logic verified.")
        else:
            print("\nFAILURE: Account not found in list.")
            
    except Exception as e:
        print(f"\nERROR during verification: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    verify_smartstore_setup()
