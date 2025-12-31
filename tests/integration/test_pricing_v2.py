import pytest
import uuid
import asyncio
from datetime import datetime, timezone
from app.db import get_session
from app.models import Product, CostComponent, MarketAccount, MarketListing, ProfitSnapshot, PricingRecommendation, MarketFeePolicy
from app.services.pricing.profit_guard import ProfitGuard
from app.services.pricing.recommender import PricingRecommender
from app.services.pricing.enforcer import PriceEnforcer

@pytest.fixture
def db_session():
    session = next(get_session())
    # 기존 데이터 정리
    session.query(PricingRecommendation).delete()
    session.query(ProfitSnapshot).delete()
    session.query(MarketFeePolicy).delete()
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.mark.asyncio
async def test_enforce_lite_logic(db_session):
    """
    ENFORCE_LITE 모드가 역마진 상품만 처리하고 정상 상품은 무시하는지 검증
    """
    uid = uuid.uuid4().hex[:8]
    
    # 수수료 정책 설정 (5%)
    db_session.add(MarketFeePolicy(market_code="COUPANG", fee_rate=0.05))
    db_session.flush()

    # 1. 역마진 상품 생성 
    # selling_price = 26050, Cost = 25000 -> Profit = -252 (Risk)
    # Target = 31250 (19.9% increase) -> Pass Safety
    risk_prod_id = uuid.uuid4()
    db_session.add(Product(id=risk_prod_id, name=f"Risk Product {uid}", selling_price=26050, status="ACTIVE"))
    db_session.flush()
    db_session.add(CostComponent(product_id=risk_prod_id, vendor="ownerclan", supply_price=23000, shipping_cost=2000, platform_fee_rate=0.05, extra_fee=0))
    
    # 2. 정상 마진 상품 생성 (판매가 31,000원으로 조정하여 안전장치 통과)
    # Target = 27500 (11.2% decrease) -> Pass Safety
    safe_prod_id = uuid.uuid4()
    db_session.add(Product(id=safe_prod_id, name=f"Safe Product {uid}", selling_price=31000, status="ACTIVE"))
    db_session.flush()
    db_session.add(CostComponent(product_id=safe_prod_id, vendor="ownerclan", supply_price=20000, shipping_cost=2000, platform_fee_rate=0.05, extra_fee=0))
    
    account_id = uuid.uuid4()
    db_session.add(MarketAccount(id=account_id, name=f"Test Acc {uid}", market_code="COUPANG", is_active=True))
    db_session.flush()

    # 스냅샷 생성
    guard = ProfitGuard(db_session)
    risk_snap = guard.analyze_product(risk_prod_id, "COUPANG", 26050)
    guard.save_snapshot(risk_snap)
    
    safe_snap = guard.analyze_product(safe_prod_id, "COUPANG", 31000)
    guard.save_snapshot(safe_snap)
    db_session.commit()
    
    # 권고 생성
    recommender = PricingRecommender(db_session)
    risk_rec = recommender.recommend_for_product(risk_prod_id, "COUPANG", account_id, 26050)
    safe_rec = recommender.recommend_for_product(safe_prod_id, "COUPANG", account_id, 31000)
    
    db_session.add(risk_rec)
    db_session.add(safe_rec)
    db_session.commit()

    # 3. ENFORCE_LITE 실행
    enforcer = PriceEnforcer(db_session)
    await enforcer.process_recommendations(mode="ENFORCE_LITE")
    
    db_session.refresh(risk_rec)
    db_session.refresh(safe_rec)
    
    # 역마진 상품은 APPLIED 상태여야 함
    assert risk_rec.status == "APPLIED"
    # 정상 상품은 여전히 PENDING 상태여야 함 (안전장치 통과했지만 Lite 모드라 스킵됨)
    assert safe_rec.status == "PENDING"

@pytest.mark.asyncio
async def test_pricing_api_endpoints(db_session):
    """
    admin.py에 추가된 가격 권고 API 엔드포인트 검증
    """
    from app.api.endpoints.admin import apply_pricing_recommendation, get_pricing_recommendations
    uid = uuid.uuid4().hex[:8]

    # 테스트 데이터 생성
    prod_id = uuid.uuid4()
    db_session.add(Product(id=prod_id, name=f"API Test Product {uid}", selling_price=10000))
    
    acc_id = uuid.uuid4()
    db_session.add(MarketAccount(id=acc_id, name=f"API Test Acc {uid}", market_code="NAVER", credentials={}, is_active=True))
    db_session.flush()
    
    rec = PricingRecommendation(
        product_id=prod_id,
        market_account_id=acc_id,
        current_price=10000,
        recommended_price=11000,
        status="PENDING"
    )
    db_session.add(rec)
    db_session.commit()
    reco_id = str(rec.id)
    
    # 1. 목록 조회 API 검증
    result_list = get_pricing_recommendations(status="PENDING", limit=50, session=db_session)
    assert any(str(r.id) == reco_id for r in result_list)
    
    # 2. 수동 승인(적용) API 검증
    resp = await apply_pricing_recommendation(reco_id=reco_id, session=db_session)
    assert resp["success"] is True
    
    db_session.refresh(rec)
    assert rec.status == "APPLIED"
