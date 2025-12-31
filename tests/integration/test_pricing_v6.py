import pytest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from app.db import get_session
from app.models import (
    Product, PricingStrategy, PricingRecommendation, 
    PricingExperiment, ProductExperimentMapping, TuningRecommendation,
    MarketAccount, PricingSettings, MarketListing, CostComponent
)
from app.services.pricing.recommender import PricingRecommender
from app.services.pricing.enforcer import PriceEnforcer
from app.services.pricing.strategy_monitor import StrategyMonitor
from app.services.pricing.drift_detector import DriftDetector
from app.services.pricing.strategy_tuner import StrategyTuner

@pytest.fixture
def db_session():
    session = next(get_session())
    try:
        yield session
    finally:
        session.rollback()
        session.close()

def test_strategy_ab_testing_and_monitoring(db_session):
    uid = uuid.uuid4().hex[:8]
    
    # 1. 두 개의 전략 생성 (A: 보수적, B: 공격적)
    strat_a = PricingStrategy(name=f"CONTROL_STRAT_{uid}", target_margin=0.20, min_margin_gate=0.15, max_price_delta=0.10)
    strat_b = PricingStrategy(name=f"TEST_STRAT_{uid}", target_margin=0.10, min_margin_gate=0.05, max_price_delta=0.40)
    db_session.add(strat_a)
    db_session.add(strat_b)
    db_session.flush()
    
    # 2. 실험 생성 (전략 오버라이드 포함)
    exp = PricingExperiment(
        name=f"Strategy Comparison {uid}",
        status="ACTIVE",
        test_ratio=1.0, # 모든 할당을 TEST로 유도 (강제)
        config_variant={"strategy_id": str(strat_b.id)}
    )
    db_session.add(exp)
    db_session.flush()
    
    # 3. 상품 생성 및 실험군 할당
    prod = Product(name=f"AB Test Prod {uid}", selling_price=30000, status="ACTIVE")
    db_session.add(prod)
    db_session.flush()
    
    mapping = ProductExperimentMapping(product_id=prod.id, experiment_id=exp.id, group="TEST")
    db_session.add(mapping)
    
    acc_id = uuid.uuid4()
    db_session.add(MarketAccount(id=acc_id, name=f"Acc {uid}", market_code="COUPANG"))
    db_session.add(PricingSettings(market_account_id=acc_id, auto_mode="SHADOW"))
    db_session.add(CostComponent(product_id=prod.id, vendor="ownerclan", supply_price=20000, shipping_cost=2000))
    db_session.flush()
    
    # 4. Recommender 실행 (실험군이므로 strat_b가 적용되어야 함)
    recommender = PricingRecommender(db_session)
    reco = recommender.recommend_for_product(prod.id, "COUPANG", acc_id, 30000)
    
    assert reco is not None
    assert reco.strategy_id == strat_b.id
    assert reco.expected_margin == 0.10 # strat_b의 마진
    
    # 5. 수동으로 여러 권고안 생성 (통계 집계 테스트용)
    reco.status = "APPLIED"
    db_session.add(reco)
    
    for i in range(5):
        r = PricingRecommendation(
            product_id=prod.id,
            market_account_id=acc_id,
            current_price=30000,
            recommended_price=25000,
            expected_margin=0.10,
            strategy_id=strat_b.id,
            status="REJECTED" if i < 3 else "APPLIED"
        )
        db_session.add(r)
    
    db_session.commit()
    
    # 6. StrategyMonitor 검증
    monitor = StrategyMonitor(db_session)
    metrics = monitor.get_strategy_metrics(days=1)
    
    strat_b_metrics = next((m for m in metrics if m["strategy_id"] == strat_b.id), None)
    assert strat_b_metrics is not None
    assert strat_b_metrics["recommendation_count"] >= 6
    assert strat_b_metrics["applied_count"] >= 3
    assert strat_b_metrics["rejected_count"] == 3
    assert strat_b_metrics["avg_expected_margin"] == 0.10

def test_drift_detection_and_tuning(db_session):
    uid = uuid.uuid4().hex[:8]
    
    # 1. 제약이 심한 전략 생성
    strat = PricingStrategy(name=f"Restrictive_{uid}", target_margin=0.15, min_margin_gate=0.10, max_price_delta=0.05)
    db_session.add(strat)
    db_session.flush()
    
    # 2. 계정 및 상품 생성 (FK 준수)
    acc_id = uuid.uuid4()
    db_session.add(MarketAccount(id=acc_id, name=f"Acc Drift {uid}", market_code="COUPANG"))
    db_session.flush()

    # 3. 대량의 REJECTED 데이터 생성 (Drift 유발)
    for _ in range(10):
        prod_id = uuid.uuid4()
        r = PricingRecommendation(
            product_id=prod_id,
            market_account_id=acc_id,
            current_price=20000,
            recommended_price=25000,
            expected_margin=0.15, # strategy.target_margin과 동일하게 설정하여 Margin Drift 방지
            strategy_id=strat.id,
            status="REJECTED"
        )
        db_session.add(r)
    db_session.commit()
    
    # 3. DriftDetector 실행
    detector = DriftDetector(db_session)
    signals = detector.detect_drifts(days=1)
    
    # 4. StrategyTuner 실행
    tuner = StrategyTuner(db_session)
    new_recos = tuner.run_tuning_cycle()
    
    # 최소 1개 이상의 권고안이 생성되어야 하며, 그중 본 테스트의 전략에 대한 SAFETY_SATURATION이 포함되어야 함
    assert len(new_recos) >= 1
    reco = next((r for r in new_recos if r.strategy_id == strat.id and r.reason_code == "SAFETY_SATURATION"), None)
    assert reco is not None, f"No SAFETY_SATURATION recommendation found for strategy {strat.id}"
    
    assert reco.strategy_id == strat.id
    assert reco.reason_code == "SAFETY_SATURATION"
    assert "max_price_delta" in reco.suggested_config
    assert reco.suggested_config["max_price_delta"] == 0.15 # 0.05 + 0.10
    
    # 5. 권고 적용
    success = tuner.apply_recommendation(reco.id)
    assert success is True
    
    db_session.refresh(strat)
    assert strat.max_price_delta == 0.15
    assert reco.status == "APPLIED"
