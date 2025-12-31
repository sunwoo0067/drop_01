import pytest
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import (
    Product, MarketAccount, MarketListing, PricingStrategy, 
    PricingRecommendation, AutonomyPolicy, AutonomyDecisionLog, SystemSetting
)
from app.services.pricing.enforcer import PriceEnforcer
from app.services.pricing.governance_manager import GovernanceManager
from app.services.pricing.segment_resolver import SegmentResolver

@pytest.mark.asyncio
async def test_autonomy_tier_gating_logic(db_session: Session):
    """자율 등급(Tier)에 따른 집행 제어 로직을 검증합니다."""
    
    # 기초 데이터 세팅
    product = Product(name="Autonomy Gate Test", lifecycle_stage="STEP_1")
    account = MarketAccount(name="Test Coupang", market_code="COUPANG", credentials={})
    db_session.add_all([product, account])
    db_session.flush()

    listing = MarketListing(
        product_id=product.id, 
        market_account_id=account.id, 
        market_item_id=f"ITEM-{uuid.uuid4()}",
        category_code="CAT_A"
    )
    # 안전장치 통과를 위해 max_price_delta 넉넉히 설정
    strategy = PricingStrategy(name="Aggressive Strategy", target_margin=0.1, min_margin_gate=0.05, max_price_delta=0.5)
    db_session.add_all([listing, strategy])
    db_session.flush()

    # 세그먼트 키 생성
    resolver = SegmentResolver()
    metadata = {
        "vendor": "COUPANG", "channel": "COUPANG", "category_code": "CAT_A",
        "strategy_id": strategy.id, "lifecycle_stage": "STEP_1"
    }
    segment_key = resolver.get_segment_key(metadata)
    
    # 초기 정책 (Tier 0: Manual)
    policy = AutonomyPolicy(
        segment_key=segment_key, vendor="COUPANG", channel="COUPANG", 
        category_code="CAT_A", strategy_id=strategy.id, tier=0, status="ACTIVE"
    )
    db_session.add(policy)
    db_session.commit()

    enforcer = PriceEnforcer(db_session)

    # [Scenario A] Tier 0 (Manual)
    reco_0 = PricingRecommendation(
        product_id=product.id, market_account_id=account.id, strategy_id=strategy.id,
        current_price=20000, recommended_price=18000, confidence=0.99, 
        expected_margin=0.12, status="PENDING"
    )
    db_session.add(reco_0)
    db_session.commit()

    await enforcer.enforce(reco_0, mode="ENFORCE_AUTO")
    db_session.refresh(reco_0)
    assert reco_0.status == "PENDING"

    # [Scenario B] Tier 2 (Auto High-Conf)
    policy.tier = 2
    db_session.commit()
    
    # 새로운 권고안으로 중복 방지
    reco_2 = PricingRecommendation(
        product_id=product.id, market_account_id=account.id, strategy_id=strategy.id,
        current_price=20000, recommended_price=18500, confidence=0.99, 
        expected_margin=0.13, status="PENDING"
    )
    db_session.add(reco_2)
    db_session.commit()

    await enforcer.enforce(reco_2, mode="ENFORCE_AUTO")
    db_session.refresh(reco_2)
    assert reco_2.status == "APPLIED"

@pytest.mark.asyncio
async def test_global_kill_switch_and_risk_mitigation(db_session: Session):
    """전역 킬스위치 및 저마진 리스크 대응 로직을 검증합니다."""
    
    gov = GovernanceManager(db_session)
    enforcer = PriceEnforcer(db_session)
    
    # 기초 데이터 세팅
    product = Product(name="KillSwitch Test", lifecycle_stage="STEP_1")
    account = MarketAccount(name="Test Coupang 2", market_code="COUPANG", credentials={})
    db_session.add_all([product, account])
    db_session.flush()

    listing = MarketListing(
        product_id=product.id, 
        market_account_id=account.id, 
        market_item_id=f"ITEM-{uuid.uuid4()}",
        category_code="CAT_B"
    )
    strategy = PricingStrategy(name="Stable Strategy", target_margin=0.2, min_margin_gate=0.15, max_price_delta=0.5)
    db_session.add_all([listing, strategy])
    db_session.flush()

    resolver = SegmentResolver()
    metadata = {"vendor": "COUPANG", "channel": "COUPANG", "category_code": "CAT_B", "strategy_id": strategy.id, "lifecycle_stage": "STEP_1"}
    segment_key = resolver.get_segment_key(metadata)
    
    policy = AutonomyPolicy(segment_key=segment_key, tier=3, status="ACTIVE")
    db_session.add(policy)
    db_session.commit()

    # [Scenario A] 전역 킬스위치 작동
    gov.set_global_kill_switch(enabled=True)
    
    reco_1 = PricingRecommendation(
        product_id=product.id, market_account_id=account.id, strategy_id=strategy.id,
        current_price=50000, recommended_price=48000, confidence=0.99, expected_margin=0.18, status="PENDING"
    )
    db_session.add(reco_1)
    db_session.commit()

    await enforcer.enforce(reco_1, mode="ENFORCE_AUTO")
    db_session.refresh(reco_1)
    assert reco_1.status == "PENDING"

    # [Scenario B] 킬스위치 OFF 및 역마진 리스크 자동 대응 (Tier 1 Enforce Lite)
    gov.set_global_kill_switch(enabled=False)
    policy.tier = 1
    db_session.commit()

    reco_risk = PricingRecommendation(
        product_id=product.id, market_account_id=account.id, strategy_id=strategy.id,
        current_price=50000, recommended_price=55000, confidence=0.80, # 10% 상승
        expected_margin=0.01, status="PENDING"
    )
    db_session.add(reco_risk)
    db_session.commit()

    await enforcer.enforce(reco_risk, mode="ENFORCE_AUTO")
    db_session.refresh(reco_risk)
    assert reco_risk.status == "APPLIED"
