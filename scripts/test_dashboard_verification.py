from app.db import SessionLocal
from app.services.analytics.coupang_policy import CoupangSourcingPolicyService
from app.services.analytics.coupang_stats import CoupangAnalyticsService
from app.models import MarketListing, MarketAccount
from datetime import datetime, timezone, timedelta
import uuid
from sqlalchemy import select

def test_dashboard_flow():
    session = SessionLocal()
    category_code = 'DASH_CAT'
    
    try:
        account = session.execute(select(MarketAccount).where(MarketAccount.market_code == 'COUPANG')).scalars().first()
        if not account:
            print("Coupang account not found.")
            return

        print("--- Step 1: Triggering PENALTY (Critical Errors) ---")
        # 최근 3건 실패 (치명적 에러 포함)
        for i in range(3):
            l = MarketListing(
                id=uuid.uuid4(),
                product_id=uuid.uuid4(),
                market_account_id=account.id,
                market_item_id=f"DASH_FAIL_{i}_{uuid.uuid4()}",
                category_code=category_code,
                status='DENIED',
                rejection_reason={"message": "브랜드 유통경로 미비 불가"}, # Critical
                linked_at=datetime.now(timezone.utc)
            )
            session.add(l)
        session.flush()
        
        # 정책 평가 -> 이벤트 자동 기록되어야 함
        CoupangSourcingPolicyService.evaluate_category_policy(session, category_code)
        
        print("\n--- Step 2: Triggering RECOVERY (Excellence) ---")
        # 7일간 5건 성공 (3개 다른 상품, 2일간 분포)
        for i in range(5):
            l = MarketListing(
                id=uuid.uuid4(),
                product_id=uuid.uuid4(), # different products
                market_account_id=account.id,
                market_item_id=f"DASH_SUCCESS_{i}_{uuid.uuid4()}",
                category_code=category_code,
                status='ACTIVE', # SUCCESS
                linked_at=datetime.now(timezone.utc) - timedelta(days=i%2) # 2 days distribution
            )
            session.add(l)
        session.flush()
        
        # 정책 평가 -> 이벤트 자동 기록되어야 함
        CoupangSourcingPolicyService.evaluate_category_policy(session, category_code)
        
        # API 로직 직접 호출하여 확인
        from app.api.endpoints.coupang_dashboard import get_adaptive_dashboard_stats
        stats = get_adaptive_dashboard_stats(session)
        
        print("\n--- Dashboard API Data (Verified) ---")
        print(f"Total Categories: {stats['total_categories']}")
        print(f"Status Distribution: {stats['status_distribution']}")
        print(f"Recent Drift Logs (Penalty): {len(stats['drift_logs'])}")
        print(f"Recent Recovery Logs (Recovery): {len(stats['recovery_logs'])}")
        print(f"Failure Modes (Heatmap): {stats['failure_modes']}")

    finally:
        session.rollback()
        session.close()

if __name__ == "__main__":
    test_dashboard_flow()
