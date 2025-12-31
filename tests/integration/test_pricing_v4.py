import pytest
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from app.db import get_session
from app.models import (
    Product, CostComponent, MarketAccount, ProfitSnapshot, 
    PricingRecommendation, PriceChangeLog, PricingSettings, MarketFeePolicy,
    PricingExperiment, ProductExperimentMapping
)
from app.services.pricing.recommender import PricingRecommender
from app.services.pricing.enforcer import PriceEnforcer
from app.services.pricing.optimizer import LearningLoop

@pytest.fixture
def db_session():
    session = next(get_session())
    # 기존 데이터 정리
    session.query(PricingRecommendation).delete()
    session.query(ProfitSnapshot).delete()
    session.query(PriceChangeLog).delete()
    session.query(PricingSettings).delete()
    session.query(MarketFeePolicy).delete()
    session.query(ProductExperimentMapping).delete()
    session.query(PricingExperiment).delete()
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.mark.asyncio
async def test_experiment_routing_and_optimization(db_session):
    """
    A/B 테스트 정책 라우팅 및 자가 학습 루프(최적화) 흐름 검증
    """
    uid = uuid.uuid4().hex[:8]
    db_session.add(MarketFeePolicy(market_code="COUPANG", fee_rate=0.05))
    
    acc_id = uuid.uuid4()
    db_session.add(MarketAccount(id=acc_id, name=f"Exp Acc {uid}", market_code="COUPANG", is_active=True))
    
    # 기본 설정: Threshold 0.95
    db_session.add(PricingSettings(market_account_id=acc_id, auto_mode="ENFORCE_AUTO", confidence_threshold=0.95))
    db_session.flush()

    # 실험 생성: Threshold를 0.85로 낮추는 실험군 설정
    exp = PricingExperiment(
        name=f"Threshold Test {uid}",
        status="ACTIVE",
        test_ratio=1.0, # 테스트를 위해 모든 신규 할당을 TEST군으로 유도
        config_variant={"confidence_threshold": 0.85}
    )
    db_session.add(exp)
    db_session.flush()

    # 상품 생성 (Confidence 0.90 예상)
    # Price 28200, Cost ~23150 -> Target 27500 (-2.4% delta < 10% -> +0.05)
    # Confidence = 0.8 + 0.05 = 0.85 -> 딱 0.85 혹은 0.90 예상
    prod_id = uuid.uuid4()
    db_session.add(Product(id=prod_id, name=f"Exp Prod {uid}", selling_price=28200, status="ACTIVE"))
    db_session.flush()
    db_session.add(CostComponent(product_id=prod_id, vendor="ownerclan", supply_price=20000, shipping_cost=2000, platform_fee_rate=0.05))
    db_session.flush()

    # 1. 권고 생성 시 실험군 할당 확인
    recommender = PricingRecommender(db_session)
    rec = recommender.recommend_for_product(prod_id, "COUPANG", acc_id, 28200)
    
    assert rec is not None
    assert rec.experiment_id == exp.id
    assert rec.experiment_group == "TEST"
    # Confidence 0.8 + 0.05(Small delta) = 0.85
    assert rec.confidence >= 0.85
    
    db_session.add(rec)
    db_session.commit()

    # 2. 대조군(CONTROL) 상품 수동 할당 및 권고 생성 (데이터 부족 방지)
    control_prod_id = uuid.uuid4()
    db_session.add(Product(id=control_prod_id, name=f"Control Prod {uid}", selling_price=30000, status="ACTIVE"))
    db_session.flush()
    db_session.add(ProductExperimentMapping(product_id=control_prod_id, experiment_id=exp.id, group="CONTROL"))
    db_session.flush()
    db_session.add(CostComponent(product_id=control_prod_id, vendor="ownerclan", supply_price=20000, shipping_cost=2000, platform_fee_rate=0.05))
    db_session.flush()
    
    control_rec = recommender.recommend_for_product(control_prod_id, "COUPANG", acc_id, 30000)
    db_session.add(control_rec)
    db_session.commit()

    # 3. Enforcer 실행 시 실험 정책(0.85)에 의해 APPLIED 되는지 확인
    # TEST군은 Confidence 0.85로 APPLIED (실험 정책 0.85 충족)
    # CONTROL군은 Confidence 0.85면 PENDING (기본 설정 0.95 기준)
    enforcer = PriceEnforcer(db_session)
    await enforcer.enforce(rec, mode="AUTO")
    await enforcer.enforce(control_rec, mode="AUTO")
    
    db_session.refresh(rec)
    db_session.refresh(control_rec)
    assert rec.status == "APPLIED"
    assert control_rec.status == "PENDING"

    # 4. Learning Loop 검증
    # TEST군 성과가 더 좋으므로 (Applied 1/1 vs 0/1), 이를 적용하면 PricingSettings가 업데이트되어야 함
    optimizer = LearningLoop(db_session)
    opt_result = optimizer.finalize_and_optimize(exp.id)
    
    assert opt_result["success"] is True
    assert opt_result["winner"] == "TEST"
    
    # PricingSettings 업데이트 확인
    settings = db_session.query(PricingSettings).filter_by(market_account_id=acc_id).first()
    assert settings.confidence_threshold == 0.85
    
    # 실험 상태 변경 확인
    db_session.refresh(exp)
    assert exp.status == "APPLIED"
