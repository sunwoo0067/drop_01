import pytest
import uuid
import asyncio
from datetime import datetime, timezone
from app.db import get_session
from app.models import (
    Product, CostComponent, MarketAccount, PricingRecommendation, 
    PricingSettings, MarketFeePolicy, MarketListing, PricingStrategy, CategoryStrategyMapping,
    OrderItem, ProfitSnapshot, PriceChangeLog, MarketBase, DropshipBase
)
from app.services.pricing.recommender import PricingRecommender
from app.services.pricing.enforcer import PriceEnforcer

@pytest.fixture
def db_session():
    session = next(get_session())
    # 데이터 정리 생략 (Unique ID 사용으로 격리)
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.mark.asyncio
async def test_category_and_product_strategy_priority(db_session):
    """
    카테고리별 전략 적용 및 상품별 오버라이드 우선순위 검증
    """
    uid = uuid.uuid4().hex[:8]
    db_session.add(MarketFeePolicy(market_code="COUPANG", fee_rate=0.05))
    
    # 1. 전략 정의
    aggressive = PricingStrategy(name=f"AGG_G_{uid}", target_margin=0.05, min_margin_gate=0.02, max_price_delta=0.40)
    stable = PricingStrategy(name=f"STABLE_{uid}", target_margin=0.15, min_margin_gate=0.10, max_price_delta=0.20)
    db_session.add(aggressive)
    db_session.add(stable)
    db_session.flush()

    # 2. 카테고리 매핑: 'ELEC_{uid}' 카테고리는 AGGRESSIVE
    cat_code = f"ELEC_{uid}"
    db_session.add(CategoryStrategyMapping(category_code=cat_code, strategy_id=aggressive.id))
    db_session.flush()

    acc_id = uuid.uuid4()
    db_session.add(MarketAccount(id=acc_id, name=f"Strat Acc {uid}", market_code="COUPANG", is_active=True))
    db_session.add(PricingSettings(market_account_id=acc_id, auto_mode="ENFORCE_AUTO"))
    db_session.flush()

    # Case A: 카테고리 전략 (AGGRESSIVE -> 5% Margin)
    prod_a = Product(name=f"ELEC Prod {uid}", selling_price=23000, status="ACTIVE")
    db_session.add(prod_a)
    db_session.flush()
    
    db_session.add(MarketListing(product_id=prod_a.id, market_account_id=acc_id, market_item_id=f"ITEM_A_{uid}", category_code=cat_code))
    db_session.add(CostComponent(product_id=prod_a.id, vendor="ownerclan", supply_price=20000, shipping_cost=2000, platform_fee_rate=0.05))
    
    # Case B: 상품 오버라이드 (Category는 ELEC_{uid}이지만 Product Strategy는 STABLE 지정 -> 15% Margin)
    prod_b = Product(name=f"Override Prod {uid}", selling_price=23000, status="ACTIVE", strategy_id=stable.id)
    db_session.add(prod_b)
    db_session.flush()
    
    db_session.add(MarketListing(product_id=prod_b.id, market_account_id=acc_id, market_item_id=f"ITEM_B_{uid}", category_code=cat_code))
    db_session.add(CostComponent(product_id=prod_b.id, vendor="ownerclan", supply_price=20000, shipping_cost=2000, platform_fee_rate=0.05))
    
    db_session.commit()

    recommender = PricingRecommender(db_session)
    
    # 1. ELEC 상품: AGGRESSIVE(5%) 적용 확인
    rec_a = recommender.recommend_for_product(prod_a.id, "COUPANG", acc_id, 23000)
    assert rec_a.expected_margin == 0.05
    assert rec_a.recommended_price >= 24000 # 5% 마진 기준
    
    # 2. Override 상품: STABLE(15%) 적용 확인 (카테고리보다 우선)
    rec_b = recommender.recommend_for_product(prod_b.id, "COUPANG", acc_id, 23000)
    assert rec_b.expected_margin == 0.15
    assert rec_b.recommended_price >= 27000 # 15% 마진 기준

@pytest.mark.asyncio
async def test_strategy_based_guardrails(db_session):
    """
    전략에 따른 동적 가드레일(max_price_delta) 검증
    """
    uid = uuid.uuid4().hex[:8]
    db_session.add(MarketFeePolicy(market_code="COUPANG", fee_rate=0.05))
    
    # AGGRESSIVE: 40% 변동 허용 / NORMAL: 20% 변동 허용
    agg = PricingStrategy(name=f"AGG_{uid}", target_margin=0.05, min_margin_gate=0.02, max_price_delta=0.40)
    norm = PricingStrategy(name=f"NORM_{uid}", target_margin=0.15, min_margin_gate=0.10, max_price_delta=0.20)
    db_session.add(agg)
    db_session.add(norm)
    db_session.flush()

    acc_id = uuid.uuid4()
    db_session.add(MarketAccount(id=acc_id, name=f"Guard Acc {uid}", market_code="COUPANG", is_active=True))
    db_session.flush()

    # 30% 가격 변화 시나리오
    # Current 10000 -> Rec 13000 (30% delta)
    prod_agg = Product(name="Agg", selling_price=10000, strategy_id=agg.id)
    db_session.add(prod_agg)
    db_session.flush()
    db_session.add(MarketListing(product_id=prod_agg.id, market_account_id=acc_id, market_item_id="A", category_code="X"))
    
    prod_norm = Product(name="Norm", selling_price=10000, strategy_id=norm.id)
    db_session.add(prod_norm)
    db_session.flush()
    db_session.add(MarketListing(product_id=prod_norm.id, market_account_id=acc_id, market_item_id="N", category_code="X"))
    
    db_session.commit()

    enforcer = PriceEnforcer(db_session)
    
    # AGGRESSIVE는 30% 변동도 허용 (40% 상한) -> REJECTED 되지 않아야 함
    rec_agg = PricingRecommendation(
        product_id=prod_agg.id, 
        market_account_id=acc_id, 
        current_price=10000, 
        recommended_price=13000, 
        status="PENDING"
    )
    db_session.add(rec_agg)
    db_session.flush() # Make it persistent but don't commit yet to see if it survives
    
    await enforcer.enforce(rec_agg, mode="SHADOW") 
    # db_session.refresh(rec_agg) is not needed if expire_on_commit=False, 
    # but since enforcer commits, let's ensure it's still attached.
    assert rec_agg.status == "PENDING"
    
    # NORMAL은 30% 변동 거부 (20% 상한) -> REJECTED 되어야 함
    rec_norm = PricingRecommendation(
        product_id=prod_norm.id, 
        market_account_id=acc_id, 
        current_price=10000, 
        recommended_price=13000, 
        status="PENDING"
    )
    db_session.add(rec_norm)
    db_session.flush()
    
    await enforcer.enforce(rec_norm, mode="SHADOW")
    # Refresh only if truly needed, but let's check status directly
    assert rec_norm.status == "REJECTED"
