"""
Analytics API Endpoints

판매 데이터 분석 및 관련 API 엔드포인트를 제공합니다.
"""
import uuid
import logging
from typing import List, Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.db import get_session
from app.services.sales_analytics_service import SalesAnalyticsService
from app.services.market_service import MarketService
from app.models import (
    SalesAnalytics, Product, ProductOption, Order, OrderItem, MarketListing,
    SupplierItemRaw, SourcingCandidate, MarketAccount
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================================
# Request/Response Models
# ============================================================================

class AnalyzeProductSalesIn(BaseModel):
    """제품 판매 분석 요청 모델"""
    product_id: uuid.UUID = Field(..., description="분석할 제품 ID")
    period_type: str = Field(default="weekly", description="분석 기간 유형 (daily, weekly, monthly)")
    period_count: int = Field(default=4, ge=1, le=12, description="분석할 기간 수")


class OptionPerformanceOut(BaseModel):
    """옵션별 성과 모델"""
    option_id: str
    option_name: str
    option_value: str
    total_quantity: int
    total_revenue: int
    total_cost: int
    total_profit: int
    avg_margin_rate: float


class SalesAnalyticsOut(BaseModel):
    """판매 분석 결과 모델"""
    id: str
    product_id: str
    period_type: str
    period_start: str
    period_end: str
    total_orders: int
    total_quantity: int
    total_revenue: int
    total_profit: int
    avg_margin_rate: float
    order_growth_rate: float
    revenue_growth_rate: float
    predicted_orders: Optional[int]
    predicted_revenue: Optional[int]
    prediction_confidence: Optional[float]
    category_trend_score: float
    market_demand_score: float
    trend_analysis: Optional[str]
    insights: Optional[List[str]]
    recommendations: Optional[List[str]]
    created_at: str
    option_performance: Optional[List[OptionPerformanceOut]] = None


class ProductPerformanceOut(BaseModel):
    """제품 성과 모델"""
    product_id: str
    product_name: str
    total_orders: int
    total_revenue: int
    total_profit: int
    avg_margin_rate: float
    order_growth_rate: float
    revenue_growth_rate: float
    predicted_orders: Optional[int]
    predicted_revenue: Optional[int]


class SalesSummaryOut(BaseModel):
    """매출 요약 모델"""
    total_revenue: int
    total_orders: int
    total_profit: int
    avg_margin_rate: float
    avg_growth_rate: float
    period_type: str
    period_start: str
    period_end: str


class SalesTrendDataPoint(BaseModel):
    """매출 추이 데이터 포인트"""
    period: str
    period_start: str
    period_end: str
    total_orders: int
    total_revenue: int
    total_profit: int
    predicted_orders: Optional[int]
    predicted_revenue: Optional[int]


class SalesTrendOut(BaseModel):
    """매출 추이 모델"""
    period_type: str
    data_points: List[SalesTrendDataPoint]


class StrategicReportOut(BaseModel):
    """AI 전략 보고서 응답 모델"""
    market_position: str
    swot_analysis: dict
    pricing_strategy: str
    action_plan: List[str]
    expected_impact: str


class OptimalPriceOut(BaseModel):
    """최적 가격 제안 응답 모델"""
    optimal_price: int
    strategy: str
    reason: str
    expected_margin_rate: float
    impact: str
    market_code: Optional[str] = None
    account_id: Optional[str] = None
    market_item_id: Optional[str] = None

class UpdatePriceIn(BaseModel):
    """가격 수정 요청 모델"""
    market_code: str = Field(..., description="마켓 코드 (COUPANG, SMARTSTORE)")
    account_id: uuid.UUID = Field(..., description="마켓 계정 ID")
    market_item_id: str = Field(..., description="마켓 상품 고유 ID")
    price: int = Field(..., description="수정할 가격")

class DashboardStatsOut(BaseModel):
    """대시보드 통합 통계 모델"""
    products: dict
    orders: dict
    markets: list[dict]

class UpdatePriceOut(BaseModel):
    """가격 수정 결과 모델"""
    success: bool
    message: Optional[str] = None

class CoupangOperationalStatsOut(BaseModel):
    """쿠팡 소싱 정책 운영 지표 모델"""
    summary: dict
    grade_distribution: dict
    time_series: List[dict]
    guardrails: Optional[dict] = None


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/analyze-product", response_model=SalesAnalyticsOut)
async def analyze_product_sales(
    payload: AnalyzeProductSalesIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """
    제품별 판매 데이터를 분석합니다.
    
    AI 기반 예측, 성장률 분석, 트렌드 점수 계산을 수행합니다.
    """
    service = SalesAnalyticsService(session)
    
    try:
        analytics = await service.analyze_product_sales(
            product_id=payload.product_id,
            period_type=payload.period_type,
            period_count=payload.period_count
        )
        
        return _analytics_to_response(analytics, session)
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error analyzing product sales: {e}")
        raise HTTPException(status_code=500, detail="판매 분석 중 오류가 발생했습니다")


@router.post("/analyze-product/{product_id}", response_model=SalesAnalyticsOut)
async def analyze_product_by_id(
    product_id: uuid.UUID,
    period_type: str = Query(default="weekly", description="분석 기간 유형"),
    period_count: int = Query(default=4, ge=1, le=12, description="분석할 기간 수"),
    session: Session = Depends(get_session)
):
    """
    제품 ID로 판매 데이터를 분석합니다.
    """
    service = SalesAnalyticsService(session)
    
    try:
        analytics = await service.analyze_product_sales(
            product_id=product_id,
            period_type=period_type,
            period_count=period_count
        )
        
        return _analytics_to_response(analytics, session)
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error analyzing product sales: {e}")
        raise HTTPException(status_code=500, detail="판매 분석 중 오류가 발생했습니다")


@router.get("/product/{product_id}", response_model=SalesAnalyticsOut)
async def get_product_analytics(
    product_id: uuid.UUID,
    period_type: str = Query(default="weekly", description="분석 기간 유형"),
    session: Session = Depends(get_session)
):
    """
    제품의 최신 판매 분석 결과를 조회합니다.
    """
    analytics = (
        session.execute(
            select(SalesAnalytics)
            .where(SalesAnalytics.product_id == product_id)
            .where(SalesAnalytics.period_type == period_type)
            .order_by(SalesAnalytics.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    
    if not analytics:
        raise HTTPException(status_code=404, detail="판매 분석 결과를 찾을 수 없습니다")
    
    return _analytics_to_response(analytics, session)


@router.get("/top-performing", response_model=List[ProductPerformanceOut])
async def get_top_performing_products(
    limit: int = Query(default=10, ge=1, le=100, description="조회할 제품 수"),
    period_type: str = Query(default="weekly", description="분석 기간 유형"),
    session: Session = Depends(get_session)
):
    """
    상위 성과 제품 목록을 조회합니다.
    
    매출 기준 상위 N개 제품을 반환합니다.
    """
    service = SalesAnalyticsService(session)
    products = service.get_top_performing_products(limit=limit, period_type=period_type)
    
    return [
        ProductPerformanceOut(**p)
        for p in products
    ]


@router.get("/low-performing", response_model=List[ProductPerformanceOut])
async def get_low_performing_products(
    limit: int = Query(default=10, ge=1, le=100, description="조회할 제품 수"),
    period_type: str = Query(default="weekly", description="분석 기간 유형"),
    session: Session = Depends(get_session)
):
    """
    저성과 제품 목록을 조회합니다.
    
    매출 기준 하위 N개 제품을 반환합니다.
    """
    service = SalesAnalyticsService(session)
    products = service.get_low_performing_products(limit=limit, period_type=period_type)
    
    return [
        ProductPerformanceOut(**p)
        for p in products
    ]


@router.get("/product/{product_id}/options", response_model=List[OptionPerformanceOut])
async def get_product_option_performance(
    product_id: uuid.UUID,
    period_type: str = Query(default="weekly", description="분석 기간 유형"),
    period_count: int = Query(default=4, ge=1, le=12, description="분석할 기간 수"),
    session: Session = Depends(get_session)
):
    """
    특정 제품의 옵션별 판매 성과를 조회합니다.
    """
    service = SalesAnalyticsService(session)
    
    # 분석 기간 계산
    period_end = datetime.now(timezone.utc)
    if period_type == "daily":
        period_start = period_end - timedelta(days=period_count)
    elif period_type == "weekly":
        period_start = period_end - timedelta(weeks=period_count)
    elif period_type == "monthly":
        period_start = period_end - timedelta(days=period_count * 30)
    else:
        period_start = period_end - timedelta(weeks=period_count)
        
    performance = service.get_option_performance(
        product_id=product_id,
        period_start=period_start,
        period_end=period_end
    )
    
    return [
        OptionPerformanceOut(**p)
        for p in performance
    ]

@router.get("/product/{product_id}/history")
async def get_product_analytics_history(
    product_id: uuid.UUID,
    period_type: str = Query(default="weekly", description="분석 기간 유형"),
    limit: int = Query(default=12, ge=1, le=52, description="조회할 기간 수"),
    session: Session = Depends(get_session)
):
    """
    제품의 판매 분석 이력을 조회합니다.
    """
    # 제품 존재 확인
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="제품을 찾을 수 없습니다")
    
    analytics_history = (
        session.execute(
            select(SalesAnalytics)
            .where(SalesAnalytics.product_id == product_id)
            .where(SalesAnalytics.period_type == period_type)
            .order_by(SalesAnalytics.period_start.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    
    return {
        "product_id": str(product_id),
        "product_name": product.name,
        "period_type": period_type,
        "history": [
            _analytics_to_response(a, session)
            for a in analytics_history
        ]
    }


@router.get("/summary", response_model=SalesSummaryOut)
async def get_sales_summary(
    period_type: str = Query(default="weekly", description="분석 기간 유형 (daily, weekly, monthly)"),
    session: Session = Depends(get_session)
):
    """
    전체 매출 요약을 조회합니다.
    
    모든 제품의 매출, 주문, 이익, 성장률을 집계합니다.
    """
    # 기간 계산
    period_end = datetime.now(timezone.utc)
    if period_type == "daily":
        period_start = period_end - timedelta(days=1)
    elif period_type == "weekly":
        period_start = period_end - timedelta(weeks=1)
    elif period_type == "monthly":
        period_start = period_end - timedelta(days=30)
    else:
        period_start = period_end - timedelta(weeks=1)
    
    # 상위 성과 제품 분석 (이익 계산용)
    service = SalesAnalyticsService(session)
    
    # 전체 주문 아이템 조회
    order_items = (
        session.execute(
            select(OrderItem)
            .join(Order)
            .where(Order.created_at >= period_start)
            .where(Order.created_at <= period_end)
        )
        .scalars()
        .all()
    )
    
    total_orders = len(set(oi.order_id for oi in order_items))
    total_revenue = sum(oi.total_price for oi in order_items)
    
    # 옵션 정보 수동 조회 (교차 DB 대응)
    option_ids = [oi.product_option_id for oi in order_items if oi.product_option_id]
    options_map = {}
    if option_ids:
        from app.models import ProductOption
        options = session.execute(
            select(ProductOption).where(ProductOption.id.in_(option_ids))
        ).scalars().all()
        options_map = {opt.id: opt for opt in options}
    
    # 정밀 이익 계산
    total_profit = 0
    for oi in order_items:
        product = session.get(Product, oi.product_id)
        if product:
            opt = options_map.get(oi.product_option_id)
            cost_per_unit = opt.cost_price if opt else product.cost_price
            total_profit += (oi.total_price - cost_per_unit * oi.quantity)
    
    avg_margin_rate = (total_profit / total_revenue) if total_revenue > 0 else 0.0
    
    # 평균 성장률 계산
    latest_analytics = (
        session.execute(
            select(SalesAnalytics)
            .where(SalesAnalytics.period_type == period_type)
            .order_by(SalesAnalytics.created_at.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )
    
    avg_growth_rate = 0.0
    if latest_analytics:
        growth_rates = [a.revenue_growth_rate for a in latest_analytics if a.revenue_growth_rate is not None]
        avg_growth_rate = sum(growth_rates) / len(growth_rates) if growth_rates else 0.0
    
    return SalesSummaryOut(
        total_revenue=total_revenue,
        total_orders=total_orders,
        total_profit=total_profit,
        avg_margin_rate=avg_margin_rate,
        avg_growth_rate=avg_growth_rate,
        period_type=period_type,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat()
    )


@router.get("/trend", response_model=SalesTrendOut)
async def get_sales_trend(
    period_type: str = Query(default="weekly", description="분석 기간 유형 (daily, weekly, monthly)"),
    periods: int = Query(default=12, ge=1, le=52, description="조회할 기간 수"),
    session: Session = Depends(get_session)
):
    """
    매출 추이를 조회합니다.
    
    지정된 기간 동안의 매출 추이 데이터를 반환합니다.
    """
    now = datetime.now(timezone.utc)
    data_points = []
    
    for i in range(periods):
        if period_type == "weekly":
            period_end = now - timedelta(weeks=i)
            period_start = period_end - timedelta(weeks=1)
            period_label = f"{period_end.strftime('%Y-%m-%d')} ({i}주 전)"
        elif period_type == "monthly":
            period_end = now - timedelta(days=i * 30)
            period_start = period_end - timedelta(days=30)
            period_label = f"{period_end.strftime('%Y-%m')} ({i}개월 전)"
        else:
            period_end = now - timedelta(days=i)
            period_start = period_end - timedelta(days=1)
            period_label = f"{period_end.strftime('%Y-%m-%d')}"
        
        # 해당 기간의 주문 아이템 조회
        order_items = (
            session.execute(
                select(OrderItem)
                .join(Order)
                .where(Order.created_at >= period_start)
                .where(Order.created_at <= period_end)
            )
            .scalars()
            .all()
        )
        
        total_orders = len(set(oi.order_id for oi in order_items))
        total_revenue = sum(oi.total_price for oi in order_items)
        
        # 옵션 정보 수동 조회 (교차 DB 대응)
        option_ids = [oi.product_option_id for oi in order_items if oi.product_option_id]
        options_map = {}
        if option_ids:
            from app.models import ProductOption
            options = session.execute(
                select(ProductOption).where(ProductOption.id.in_(option_ids))
            ).scalars().all()
            options_map = {opt.id: opt for opt in options}
            
        # 정밀 이익 계산
        total_profit = 0
        for oi in order_items:
            product = session.get(Product, oi.product_id)
            if product:
                opt = options_map.get(oi.product_option_id)
                cost_per_unit = opt.cost_price if opt else product.cost_price
                total_profit += (oi.total_price - cost_per_unit * oi.quantity)
        
        # 예측 데이터 조회 (해당 기간의 최신 분석)
        predicted_orders = None
        predicted_revenue = None
        
        # 해당 기간에 대한 예측 데이터가 있는지 확인
        period_analytics = (
            session.execute(
                select(SalesAnalytics)
                .where(SalesAnalytics.period_type == period_type)
                .where(SalesAnalytics.period_start <= period_start)
                .where(SalesAnalytics.period_end >= period_end)
                .order_by(SalesAnalytics.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        
        if period_analytics:
            predicted_orders = period_analytics.predicted_orders
            predicted_revenue = period_analytics.predicted_revenue
        
        data_points.append(SalesTrendDataPoint(
            period=period_label,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            total_orders=total_orders,
            total_revenue=total_revenue,
            total_profit=total_profit,
            predicted_orders=predicted_orders,
            predicted_revenue=predicted_revenue
        ))
    
    # 최신 데이터가 먼저 오도록 정렬
    data_points.reverse()
    
    return SalesTrendOut(
        period_type=period_type,
        data_points=data_points
    )


@router.post("/bulk-analyze")
async def trigger_bulk_analytics(
    background_tasks: BackgroundTasks,
    limit: int = Query(default=50, ge=1, le=500, description="분석할 제품 수"),
    period_type: str = Query(default="weekly", description="분석 기간 유형"),
    session: Session = Depends(get_session)
):
    """
    대량 판매 분석을 백그라운드에서 실행합니다.
    
    활성 제품들의 판매 데이터를 일괄 분석합니다.
    """
    # 활성 제품 조회
    products = (
        session.execute(
            select(Product)
            .where(Product.status == "ACTIVE")
            .limit(limit)
        )
        .scalars()
        .all()
    )
    
    if not products:
        return {"status": "no_products", "message": "분석할 활성 제품이 없습니다"}
    
    # 백그라운드 작업 등록
    background_tasks.add_task(
        _execute_bulk_analytics,
        [p.id for p in products],
        period_type,
        session
    )
    
    return {
        "status": "started",
        "message": f"{len(products)}개 제품의 판매 분석을 시작했습니다",
        "product_count": len(products)
    }


@router.get("/dashboard/stats", response_model=DashboardStatsOut)
def get_dashboard_stats(
    session: Session = Depends(get_session),
    supplier_code: str = Query(default="ownerclan", alias="supplierCode"),
):
    """
    대시보드에 필요한 통합 통계 데이터를 반환합니다.
    (상품 현황, 주문 현황, 마켓별 등록 현황)
    """
    # supplier_code가 "all"이거나 비어있으면 전체 통계
    is_all = not supplier_code or supplier_code.lower() == "all"
    # 1. 상품 현황 (상세 단계별)
    # 1-1. 소싱 단계 (SourcingCandidate)
    raw_query = select(func.count(SupplierItemRaw.id))
    if not is_all:
        raw_query = raw_query.where(SupplierItemRaw.supplier_code == supplier_code)
    total_raw = session.scalar(raw_query) or 0
    
    s_query = select(SourcingCandidate.status, func.count(SourcingCandidate.id))
    if not is_all:
        s_query = s_query.where(SourcingCandidate.supplier_code == supplier_code)
    
    sourcing_stats = session.execute(s_query.group_by(SourcingCandidate.status)).all()
    sourcing_map = {status: count for status, count in sourcing_stats}

    # 1-2. 가공 단계 (Product Processing Status)
    # Product는 SourcingCandidate에서 APPROVED된 것들을 기반으로 생성됨
    product_query = select(Product.processing_status, func.count(Product.id))
    if not is_all:
        product_query = (
            product_query.join(SupplierItemRaw, SupplierItemRaw.id == Product.supplier_item_id)
            .where(SupplierItemRaw.supplier_code == supplier_code)
        )
    product_stats = session.execute(product_query.group_by(Product.processing_status)).all()
    product_map = {status: count for status, count in product_stats}

    # 라이프사이클 단계별 (STEP_1, STEP_2, STEP_3)
    lifecycle_query = select(Product.lifecycle_stage, func.count(Product.id))
    if not is_all:
        lifecycle_query = (
            lifecycle_query.join(SupplierItemRaw, SupplierItemRaw.id == Product.supplier_item_id)
            .where(SupplierItemRaw.supplier_code == supplier_code)
        )
    lifecycle_stats = session.execute(lifecycle_query.group_by(Product.lifecycle_stage)).all()
    lifecycle_map = {stage: count for stage, count in lifecycle_stats}

    # 1-3. 합계 수량 (Stock Quantity sum)
    # ProductOption에서 전체 재고 합계
    total_stock_query = select(func.sum(ProductOption.stock_quantity)).join(
        Product, ProductOption.product_id == Product.id
    )
    if not is_all:
        total_stock_query = (
            total_stock_query.join(SupplierItemRaw, SupplierItemRaw.id == Product.supplier_item_id)
            .where(SupplierItemRaw.supplier_code == supplier_code)
        )
    total_stock = session.scalar(total_stock_query) or 0

    # 2. 주문 현황
    start_of_day = datetime.now(timezone.utc).astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    order_query = select(Order.status, func.count(func.distinct(Order.id))).where(
        Order.created_at >= start_of_day
    )
    if not is_all:
        order_query = (
            order_query.join(OrderItem, OrderItem.order_id == Order.id)
            .join(Product, Product.id == OrderItem.product_id)
            .join(SupplierItemRaw, SupplierItemRaw.id == Product.supplier_item_id)
            .where(SupplierItemRaw.supplier_code == supplier_code)
        )
    order_status_counts = session.execute(order_query.group_by(Order.status)).all()
    orders_map = {status: count for status, count in order_status_counts}

    # 3. 마켓 현황 (계정별 등록 상품 수 및 리스팅 상태)
    accounts = session.execute(
        select(MarketAccount).where(MarketAccount.is_active == True)
    ).scalars().all()
    
    listing_stats = session.execute(
        select(MarketListing.market_account_id, MarketListing.status, func.count(MarketListing.id))
        .group_by(MarketListing.market_account_id, MarketListing.status)
    ).all()
    
    listing_stats_map = {}
    for acc_id, status, count in listing_stats:
        if acc_id not in listing_stats_map:
            listing_stats_map[acc_id] = {"total": 0, "active": 0, "failed": 0}
        listing_stats_map[acc_id]["total"] += count
        if status == "ACTIVE":
            listing_stats_map[acc_id]["active"] += count
        elif status in ["REJECTED", "FAILED"]:
            listing_stats_map[acc_id]["failed"] += count

    market_results = []
    for acc in accounts:
        stats_data = listing_stats_map.get(acc.id, {"total": 0, "active": 0, "failed": 0})
        market_results.append({
            "market_code": acc.market_code,
            "account_name": acc.name,
            "account_id": str(acc.id),
            "listing_count": stats_data["total"],
            "active_count": stats_data["active"],
            "failed_count": stats_data["failed"]
        })

    return {
        "products": {
            "total_raw": total_raw,
            "sourcing_pending": sourcing_map.get("PENDING", 0),
            "sourcing_approved": sourcing_map.get("APPROVED", 0),
            "refinement_pending": product_map.get("PENDING", 0),
            "refinement_processing": product_map.get("PROCESSING", 0),
            "refinement_approval_pending": product_map.get("PENDING_APPROVAL", 0),
            "refinement_failed": product_map.get("FAILED", 0),
            "refinement_completed": product_map.get("COMPLETED", 0),
            "total_stock": int(total_stock),
            "lifecycle_stages": {
                "step_1": lifecycle_map.get("STEP_1", 0),
                "step_2": lifecycle_map.get("STEP_2", 0),
                "step_3": lifecycle_map.get("STEP_3", 0)
            },
            # 레거시 호환
            "pending": sourcing_map.get("PENDING", 0), 
            "completed": product_map.get("COMPLETED", 0)
        },
        "orders": {
            "payment_completed": orders_map.get("PAYMENT_COMPLETED", 0),
            "ready": orders_map.get("READY", 0),
            "shipping": orders_map.get("SHIPPING", 0),
            "shipped": orders_map.get("SHIPPED", 0),
            "cancelled": orders_map.get("CANCELLED", 0)
        },
        "markets": market_results
    }


@router.get("/coupang/operational-stats", response_model=CoupangOperationalStatsOut)
def get_coupang_operational_stats(
    days: int = Query(default=7, ge=1, le=30),
    session: Session = Depends(get_session)
):
    """
    쿠팡 소싱 정책 운영 지표 및 가드레일 상태를 조회합니다.
    """
    from app.services.analytics.reporting import CoupangOperationalReportService
    from app.services.analytics.guardrails import CoupangGuardrailService
    
    stats = CoupangOperationalReportService.get_daily_operational_stats(session, days)
    is_critical, msg, rec = CoupangGuardrailService.check_system_integrity(session)
    
    stats["guardrails"] = {
        "is_critical": is_critical,
        "message": msg,
        "recommended_mode": rec
    }
    return stats


# ============================================================================
# Helper Functions
# ============================================================================

@router.get("/strategic-report/{product_id}", response_model=StrategicReportOut)
async def get_strategic_report(
    product_id: uuid.UUID,
    session: Session = Depends(get_session)
):
    """
    제품의 AI 전략 보고서를 생성하거나 조회합니다.
    """
    service = SalesAnalyticsService(session)
    try:
        report = await service.generate_strategic_insight(product_id)
        return report
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating strategic report: {e}")
        raise HTTPException(status_code=500, detail="전략 보고서 생성 중 오류가 발생했습니다")


@router.get("/optimal-price/{product_id}", response_model=OptimalPriceOut)
async def get_optimal_price_prediction(
    product_id: uuid.UUID,
    session: Session = Depends(get_session)
):
    """
    AI 기반 최적 가격 제안을 조회합니다.
    """
    from app.services.sourcing_recommendation_service import SourcingRecommendationService
    service = SourcingRecommendationService(session)
    try:
        prediction = await service.predict_optimal_price(product_id)
        return prediction
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error predicting optimal price: {e}")
        raise HTTPException(status_code=500, detail="최적 가격 예측 중 오류가 발생했습니다")


@router.post("/update-price", response_model=UpdatePriceOut)
async def update_market_price(
    data: UpdatePriceIn,
    db: Session = Depends(get_session)
):
    """
    마켓 상품의 판매가를 실시간으로 수정합니다.
    """
    service = MarketService(db)
    
    success, message = service.update_price(
        market_code=data.market_code,
        account_id=data.account_id,
        market_item_id=data.market_item_id,
        price=data.price
    )
    
    return UpdatePriceOut(success=success, message=message)


def _analytics_to_response(analytics: SalesAnalytics, session: Optional[Session] = None) -> SalesAnalyticsOut:
    """SalesAnalytics 모델을 응답 모델로 변환"""
    response = SalesAnalyticsOut(
        id=str(analytics.id),
        product_id=str(analytics.product_id),
        period_type=analytics.period_type,
        period_start=analytics.period_start.isoformat() if analytics.period_start else None,
        period_end=analytics.period_end.isoformat() if analytics.period_end else None,
        total_orders=analytics.total_orders,
        total_quantity=analytics.total_quantity,
        total_revenue=analytics.total_revenue,
        total_profit=analytics.total_profit,
        avg_margin_rate=analytics.avg_margin_rate,
        order_growth_rate=analytics.order_growth_rate,
        revenue_growth_rate=analytics.revenue_growth_rate,
        predicted_orders=analytics.predicted_orders,
        predicted_revenue=analytics.predicted_revenue,
        prediction_confidence=analytics.prediction_confidence,
        category_trend_score=analytics.category_trend_score,
        market_demand_score=analytics.market_demand_score,
        trend_analysis=analytics.trend_analysis,
        insights=analytics.insights or [],
        recommendations=analytics.recommendations or [],
        created_at=analytics.created_at.isoformat() if analytics.created_at else None
    )
    
    # 옵션 성과 추가 (세션이 제공된 경우에만)
    if session:
        service = SalesAnalyticsService(session)
        performance = service.get_option_performance(
            product_id=analytics.product_id,
            period_start=analytics.period_start,
            period_end=analytics.period_end
        )
        response.option_performance = [OptionPerformanceOut(**p) for p in performance]
        
    return response


async def _execute_bulk_analytics(
    product_ids: List[uuid.UUID],
    period_type: str,
    session: Session
):
    """
    대량 판매 분석 실행 (백그라운드 작업)
    
    Args:
        product_ids: 분석할 제품 ID 목록
        period_type: 분석 기간 유형
        session: 데이터베이스 세션
    """
    from app.session_factory import session_factory
    
    success_count = 0
    error_count = 0
    
    for product_id in product_ids:
        try:
            with session_factory() as db:
                service = SalesAnalyticsService(db)
                await service.analyze_product_sales(product_id, period_type=period_type)
                success_count += 1
        except Exception as e:
            logger.error(f"Failed to analyze product {product_id}: {e}")
            error_count += 1
    
    logger.info(
        f"Bulk analytics completed: {success_count} succeeded, {error_count} failed"
    )
