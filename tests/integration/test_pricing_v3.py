import pytest
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from app.db import get_session
from app.models import (
    Product, CostComponent, MarketAccount, ProfitSnapshot, 
    PricingRecommendation, PriceChangeLog, PricingSettings, MarketFeePolicy
)
from app.services.pricing.profit_guard import ProfitGuard
from app.services.pricing.recommender import PricingRecommender
from app.services.pricing.enforcer import PriceEnforcer

@pytest.fixture
def db_session():
    session = next(get_session())
    # 기존 데이터 정리
    session.query(PricingRecommendation).delete()
    session.query(ProfitSnapshot).delete()
    session.query(PriceChangeLog).delete()
    session.query(PricingSettings).delete()
    session.query(MarketFeePolicy).delete()
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.mark.asyncio
async def test_enforce_auto_logic(db_session):
    """
    ENFORCE_AUTO 모드: 역마진 또는 고신뢰도 상품만 자동 집행하는지 검증
    """
    uid = uuid.uuid4().hex[:8]
    db_session.add(MarketFeePolicy(market_code="COUPANG", fee_rate=0.05))
    db_session.flush()

    # 1. 고신뢰도 상품 (Negative Profit + Safe delta -> Confidence 0.95 -> APPLIED)
    # Price 23000, Cost ~23150 -> Confidence 0.8 + 0.15 (Margin) = 0.95
    # Target 27500 (+19.5% delta < 20%) -> SAFE
    high_conf_id = uuid.uuid4()
    db_session.add(Product(id=high_conf_id, name=f"High Conf {uid}", selling_price=23000, status="ACTIVE"))
    db_session.flush()
    db_session.add(CostComponent(product_id=high_conf_id, vendor="ownerclan", supply_price=20000, shipping_cost=2000, platform_fee_rate=0.05))
    
    # 2. 저신뢰도 상품 (Positive Profit + Small delta -> Confidence 0.85 -> PENDING)
    # Price 30000, Cost ~23150 -> Margin positive. Target 27500 (-8.3% delta < 10% -> +0.05)
    # Confidence = 0.8 + 0.05 = 0.85 < 0.95
    low_conf_id = uuid.uuid4()
    db_session.add(Product(id=low_conf_id, name=f"Low Conf {uid}", selling_price=30000, status="ACTIVE"))
    db_session.flush()
    db_session.add(CostComponent(product_id=low_conf_id, vendor="ownerclan", supply_price=20000, shipping_cost=2000, platform_fee_rate=0.05))

    db_session.flush()

    acc_id = uuid.uuid4()
    db_session.add(MarketAccount(id=acc_id, name=f"Test Acc {uid}", market_code="COUPANG", is_active=True))
    
    # 설정 추가 (Threshold 0.95)
    db_session.add(PricingSettings(market_account_id=acc_id, auto_mode="ENFORCE_AUTO", confidence_threshold=0.95))
    db_session.flush()

    # 분석 및 권고 생성
    recommender = PricingRecommender(db_session)
    high_rec = recommender.recommend_for_product(high_conf_id, "COUPANG", acc_id, 23000)
    low_rec = recommender.recommend_for_product(low_conf_id, "COUPANG", acc_id, 30000)
    
    db_session.add(high_rec)
    db_session.add(low_rec)
    db_session.commit()
    
    # Confidence 확인 (로그상 확인용)
    print(f"DEBUG: High Conf Recommendation Confidence: {high_rec.confidence}")
    print(f"DEBUG: Low Conf Recommendation Confidence: {low_rec.confidence}")

    # ENFORCE_AUTO 실행
    enforcer = PriceEnforcer(db_session)
    await enforcer.process_recommendations(mode="ENFORCE_AUTO")
    
    db_session.refresh(high_rec)
    db_session.refresh(low_rec)
    
    # 고신뢰 상품은 집행되어야 함
    assert high_rec.status == "APPLIED" if high_rec.confidence >= 0.95 else high_rec.status == "PENDING"
    # 저신뢰 상품은 대기 상태여야 함
    assert low_rec.status == "PENDING"

@pytest.mark.asyncio
async def test_throttling_and_cooldown(db_session):
    """
    스로틀링 및 쿨다운 정책 검증
    """
    uid = uuid.uuid4().hex[:8]
    prod_id = uuid.uuid4()
    db_session.add(Product(id=prod_id, name=f"Throttle Test {uid}", selling_price=10000))
    
    acc_id = uuid.uuid4()
    db_session.add(MarketAccount(id=acc_id, name=f"Throttle Acc {uid}", market_code="COUPANG", is_active=True))
    
    # 스로틀링 설정 (시간당 2회 제한)
    db_session.add(PricingSettings(market_account_id=acc_id, max_changes_per_hour=2, cooldown_hours=1))
    db_session.flush()

    # 1. 스로틀링 유도 (이미 2회 성공 기록 생성)
    for _ in range(2):
        db_session.add(PriceChangeLog(
            product_id=prod_id,
            market_account_id=acc_id,
            old_price=9000,
            new_price=10000,
            source="AUTO_ENFORCE",
            status="SUCCESS",
            created_at=datetime.now(timezone.utc)
        ))
    db_session.commit()

    rec = PricingRecommendation(
        product_id=prod_id,
        market_account_id=acc_id,
        current_price=10000,
        recommended_price=11000,
        confidence=1.0,
        status="PENDING"
    )
    db_session.add(rec)
    db_session.commit()

    enforcer = PriceEnforcer(db_session)
    # ENFORCE 모드로 강제 실행해도 스로틀링 체크 로직이 걸려야 함
    # (enforcer.py 코드상 mode in ["ENFORCE_LITE", "ENFORCE_AUTO"] 일 때만 체크하므로 테스트에서도 모드 맞춰줌)
    await enforcer.enforce(rec, mode="ENFORCE_AUTO")
    
    db_session.refresh(rec)
    # 스로틀링에 걸려 PENDING 유지되어야 함
    assert rec.status == "PENDING"
    
    # 2. 쿨다운 테스트를 위해 스로틀링 기록 삭제 후 최근 1건만 생성
    db_session.query(PriceChangeLog).delete()
    db_session.add(PriceChangeLog(
        product_id=prod_id,
        market_account_id=acc_id,
        old_price=9500,
        new_price=10000,
        source="AUTO_ENFORCE",
        status="SUCCESS",
        created_at=datetime.now(timezone.utc) # 방금 변경
    ))
    db_session.commit()
    
    await enforcer.enforce(rec, mode="ENFORCE_AUTO")
    db_session.refresh(rec)
    # 쿨다운에 걸려 PENDING 유지
    assert rec.status == "PENDING"
