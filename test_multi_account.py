import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import MarketAccount
from app.db import market_engine

def test_multi_account_activation():
    with Session(market_engine) as session:
        # 1. Clean up existing test accounts (optional, but safer)
        # session.query(MarketAccount).filter(MarketAccount.name.like("TEST_%")).delete()
        # session.commit()

        print("--- Testing Coupang Multi-Account Activation ---")
        
        # 2. Create Account 1
        name1 = f"TEST_ACC_1_{uuid.uuid4().hex[:4]}"
        acc1 = MarketAccount(
            market_code="COUPANG",
            name=name1,
            credentials={"vendor_id": "V1", "access_key": "AK1", "secret_key": "SK1"},
            is_active=True
        )
        session.add(acc1)
        session.flush()
        id1 = acc1.id
        print(f"Created and activated {name1} (ID: {id1})")

        # 3. Create Account 2
        name2 = f"TEST_ACC_2_{uuid.uuid4().hex[:4]}"
        acc2 = MarketAccount(
            market_code="COUPANG",
            name=name2,
            credentials={"vendor_id": "V2", "access_key": "AK2", "secret_key": "SK2"},
            is_active=True
        )
        session.add(acc2)
        session.flush()
        id2 = acc2.id
        print(f"Created and activated {name2} (ID: {id2})")
        
        session.commit()

        # 4. Check if both are active after creation (if both set to True)
        session.expire_all()
        a1 = session.get(MarketAccount, id1)
        a2 = session.get(MarketAccount, id2)
        
        print(f"Status after creation: {name1}.is_active={a1.is_active}, {name2}.is_active={a2.is_active}")

        if a1.is_active and a2.is_active:
            print("SUCCESS: Both accounts are active after creation.")
        else:
            print("FAILURE: One account was deactivated during creation of another.")

        # 5. Test explicit activation endpoint logic (simulated)
        print("\n--- Testing Explicit Activation ---")
        # Deactivate both first
        a1.is_active = False
        a2.is_active = False
        session.commit()
        
        # Activate A1
        a1.is_active = True
        session.add(a1)
        # Here we simulate what activate_coupang_account does: it just sets is_active=True and commits.
        # But if there's some hidden trigger, this might deactivate others.
        session.commit()
        
        # Activate A2
        a2.is_active = True
        session.add(a2)
        session.commit()
        
        session.expire_all()
        a1 = session.get(MarketAccount, id1)
        a2 = session.get(MarketAccount, id2)
        
        print(f"Status after sequential activation: {name1}.is_active={a1.is_active}, {name2}.is_active={a2.is_active}")
        
        if a1.is_active and a2.is_active:
            print("SUCCESS: Multi-account activation works in DB level.")
        else:
            print("FAILURE: DB level activation still deactivates others.")

        # Cleanup
        # session.delete(a1)
        # session.delete(a2)
        # session.commit()

if __name__ == "__main__":
    test_multi_account_activation()
