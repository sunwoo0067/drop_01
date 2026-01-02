from sqlalchemy import select, insert
from app.db import SessionLocal
from app.models import MarketListing, MarketAccount
from app.services.analytics.coupang_policy import CoupangSourcingPolicyService
from datetime import datetime, timezone
import uuid

def test_adaptive_penalty():
    session = SessionLocal()
    category_code = '64239'
    
    try:
        print(f"--- Initial Policy for {category_code} ---")
        p_init = CoupangSourcingPolicyService.evaluate_category_policy(session, category_code)
        print(f"Grade: {p_init['grade']}, Score: {p_init['score']}")

        # 1. 가상 실패 데이터 주입 (최근 7일)
        account = session.execute(select(MarketAccount).where(MarketAccount.market_code == 'COUPANG')).scalars().first()
        if not account:
            print("Coupang account not found.")
            return

        print("\nInjecting 4 recent failures...")
        new_listings = []
        for i in range(4):
            l = MarketListing(
                id=uuid.uuid4(),
                product_id=uuid.uuid4(), # dummy
                market_account_id=account.id,
                market_item_id=f"TEST_{uuid.uuid4()}", # dummy
                category_code=category_code,
                status='DENIED', # 실패
                linked_at=datetime.now(timezone.utc)
            )
            session.add(l)
            new_listings.append(l)
        session.flush()

        print("--- Updated Policy (after 4 failures) ---")
        p_updated = CoupangSourcingPolicyService.evaluate_category_policy(session, category_code)
        print(f"Grade: {p_updated['grade']}, Score: {p_updated['score']}")
        print(f"Reason: {p_updated['reason']}")

    finally:
        # DB 오염 방지를 위해 롤백
        session.rollback()
        session.close()

if __name__ == "__main__":
    from sqlalchemy import select
    test_adaptive_penalty()
