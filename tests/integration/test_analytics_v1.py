import pytest
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import Product, Order, OrderItem, ProfitSnapshot, PricingRecommendation, CostComponent, MarketAccount
from app.models_analytics import ProductDim, OrdersFact, ProfitSnapshotFact, PricingRecoFact
from app.services.analytics.etl_manager import ETLManager
from app.services.analytics.kpi_engine import KPIEngine

@pytest.fixture
def db_session():
    session = next(get_session())
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.mark.asyncio
async def test_analytics_pipeline(db_session: Session):
    """
    운영 데이터 -> ETL -> 데이터 레이크 -> KPI 엔진으로 이어지는 분석 파이프라인 검증
    """
    # 1. 테스트 데이터 준비
    prod_id = uuid.uuid4()
    product = Product(
        id=prod_id,
        name="Analytics Test Product",
        cost_price=10000,
        status="ACTIVE"
    )
    db_session.add(product)
    db_session.flush()
    
    cost = CostComponent(
        product_id=prod_id,
        vendor="ownerclan",
        supply_price=10000,
        shipping_cost=2500,
        platform_fee_rate=0.1,
        extra_fee=0
    )
    db_session.add(cost)
    
    # 주문 생성
    order = Order(
        id=uuid.uuid4(),
        order_number=f"TEST-ORD-{uuid.uuid4().hex[:6]}",
        vendor_order_id=f"MARKET-{uuid.uuid4().hex[:6]}",
        marketplace="COUPANG",
        total_amount=20000,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    db_session.add(order)
    db_session.flush()
    
    item = OrderItem(
        order_id=order.id,
        product_id=prod_id,
        product_name=product.name,
        quantity=1,
        unit_price=20000,
        total_price=20000
    )
    db_session.add(item)
    
    # 수익 스냅샷 및 권고
    snapshot = ProfitSnapshot(
        product_id=prod_id,
        channel="COUPANG",
        current_price=20000,
        estimated_profit=5500, # 20000 - (10000+2500+2000)
        margin_rate=0.275,
        is_risk=False,
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(snapshot)
    
    acc_id = uuid.uuid4()
    account = MarketAccount(id=acc_id, market_code="COUPANG", name=f"Analytics Test Acc {acc_id.hex[:6]}", is_active=True)
    db_session.add(account)
    db_session.flush()

    reco = PricingRecommendation(
        product_id=prod_id,
        market_account_id=account.id,
        current_price=20000,
        recommended_price=22000,
        status="PENDING",
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(reco)
    db_session.commit()

    # ---------------------------------------------------------
    # 2. ETL 실행
    # ---------------------------------------------------------
    etl = ETLManager(db_session)
    etl.sync_all()
    
    # 검증: 데이터 레이크에 데이터가 적재되었는가?
    prod_dim = db_session.query(ProductDim).filter_by(product_id=prod_id).first()
    assert prod_dim is not None
    assert prod_dim.name == product.name
    
    order_fact = db_session.query(OrdersFact).filter_by(order_id=order.vendor_order_id).first()
    assert order_fact is not None
    assert order_fact.sell_price == 20000
    
    # ---------------------------------------------------------
    # 3. KPI 엔진 검증
    # ---------------------------------------------------------
    kpi = KPIEngine(db_session)
    
    # 마진 트렌드
    trend = kpi.get_margin_trend(days=1)
    assert len(trend) > 0
    assert trend[0]["order_count"] >= 1
    
    # 시뮬레이션 (특정 상품 필터링)
    sim = kpi.get_what_if_simulation(product_id=prod_id)
    assert sim["pending_reco_count"] == 1
    assert sim["expected_lift"] == 2000 # (22000 - 20000)
    
    # 건전성 요약
    health = kpi.get_inventory_health()
    assert health["total_active_products"] >= 1
