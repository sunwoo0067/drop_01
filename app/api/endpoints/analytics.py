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
from app.models import SalesAnalytics, Product, Order, OrderItem

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
        
        return _analytics_to_response(analytics)
        
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
        
        return _analytics_to_response(analytics)
        
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
    
    return _analytics_to_response(analytics)


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
            _analytics_to_response(a)
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
    
    # 전체 매출 집계
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
    total_quantity = sum(oi.quantity for oi in order_items)
    total_revenue = sum(oi.total_price for oi in order_items)
    
    # 이익률 계산
    total_profit = 0
    for oi in order_items:
        product = session.get(Product, oi.product_id)
        if product:
            total_profit += (oi.total_price - product.cost_price * oi.quantity)
    
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
        total_quantity = sum(oi.quantity for oi in order_items)
        total_revenue = sum(oi.total_price for oi in order_items)
        
        # 이익 계산
        total_profit = 0
        for oi in order_items:
            product = session.get(Product, oi.product_id)
            if product:
                total_profit += (oi.total_price - product.cost_price * oi.quantity)
        
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


# ============================================================================
# Helper Functions
# ============================================================================

def _analytics_to_response(analytics: SalesAnalytics) -> SalesAnalyticsOut:
    """SalesAnalytics 모델을 응답 모델로 변환"""
    return SalesAnalyticsOut(
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
