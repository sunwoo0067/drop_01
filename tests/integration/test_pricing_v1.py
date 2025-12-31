import pytest
import uuid
from datetime import datetime, timezone
from app.db import get_session
from app.models import Product, CostComponent, MarketAccount, MarketListing, ProfitSnapshot, PricingRecommendation
from app.services.pricing.profit_guard import ProfitGuard
from app.services.pricing.recommender import PricingRecommender
from app.services.pricing.enforcer import PriceEnforcer

@pytest.fixture
def db_session():
    session = next(get_session())
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.mark.asyncio
async def test_profit_and_pricing_pipeline(db_session):
    """
    수익 분석 -> 가격 권고 -> 집행(안전장치)으로 이어지는 전체 파이프라인 통합 테스트
    """
    # 1. 초기 데이터 설정 (역마진 상황 조성)
    test_prod_id = uuid.uuid4()
    product = Product(
        id=test_prod_id,
        name=f"PR-8 Test Product {test_prod_id.hex[:8]}",
        selling_price=17000,
        status="ACTIVE"
    )
    db_session.add(product)
    db_session.flush()
    
    # 원가 12000 + 배송비 2500 = 14500 (판매가 17000 대비 저마진)
    cost = CostComponent(
        product_id=test_prod_id,
        vendor="ownerclan",
        supply_price=12000,
        shipping_cost=2500,
        platform_fee_rate=0.1,
        extra_fee=0
    )
    db_session.add(cost)
    
    account_id = uuid.uuid4()
    account = MarketAccount(
        id=account_id,
        name=f"Test Account {account_id.hex[:8]}",
        market_code="COUPANG",
        is_active=True
    )
    db_session.add(account)
    db_session.flush()
    
    listing = MarketListing(
        product_id=test_prod_id,
        market_account_id=account.id,
        market_item_id="test_market_item_v1",
        status="ACTIVE"
    )
    db_session.add(listing)
    db_session.commit()

    # ---------------------------------------------------------
    # 2. Phase 1: ProfitGuard (역마진 감지 검증)
    # ---------------------------------------------------------
    guard = ProfitGuard(db_session)
    snapshot = guard.analyze_product(test_prod_id, "COUPANG", product.selling_price)
    
    assert snapshot.is_risk is True
    assert "LOW_MARGIN" in snapshot.reason_codes
    assert snapshot.estimated_profit > 0
    
    guard.save_snapshot(snapshot)
    
    # ---------------------------------------------------------
    # 3. Phase 2: PricingRecommender (권장가 산출 검증)
    # ---------------------------------------------------------
    recommender = PricingRecommender(db_session)
    rec = recommender.recommend_for_product(
        test_prod_id, "COUPANG", account.id, product.selling_price
    )
    
    assert rec is not None
    assert rec.recommended_price > product.selling_price
    assert rec.status == "PENDING"
    
    db_session.add(rec)
    db_session.commit()
    
    # ---------------------------------------------------------
    # 4. Phase 3: PriceEnforcer (안전장치 및 집행 검증)
    # ---------------------------------------------------------
    enforcer = PriceEnforcer(db_session)
    
    # SHADOW 모드: 상태 변화가 없어야 함
    await enforcer.process_recommendations(mode="SHADOW")
    db_session.refresh(rec)
    assert rec.status == "PENDING"
    
    # 정상 범위 내 변경 집행 (ENFORCE)
    await enforcer.process_recommendations(mode="ENFORCE")
    db_session.refresh(rec)
    assert rec.status == "APPLIED"
    
    # 비정상 범위(급격한 변동) 테스트
    # 다시 PENDING 권고 생성 시뮬레이션
    unsafe_rec = PricingRecommendation(
        product_id=test_prod_id,
        market_account_id=account.id,
        current_price=10000,
        recommended_price=30000, # 200% 증가 (정상 범위를 벗어남)
        status="PENDING"
    )
    db_session.add(unsafe_rec)
    db_session.commit()
    
    await enforcer.process_recommendations(mode="ENFORCE")
    db_session.refresh(unsafe_rec)
    # 안전장치에 의해 거절되어야 함
    assert unsafe_rec.status == "REJECTED"
    assert any("Safety Rejection" in r for r in unsafe_rec.reasons)
