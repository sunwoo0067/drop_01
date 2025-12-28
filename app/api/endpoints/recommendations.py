"""
Recommendations API Endpoints

AI 기반 소싱 추천 및 관련 API 엔드포인트를 제공합니다.
"""
import uuid
import logging
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_session
from app.services.sourcing_recommendation_service import SourcingRecommendationService
from app.models import SourcingRecommendation, Product

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================================
# Request/Response Models
# ============================================================================

class GenerateRecommendationIn(BaseModel):
    """소싱 추천 생성 요청 모델"""
    product_id: uuid.UUID = Field(..., description="추천을 생성할 제품 ID")
    recommendation_type: str = Field(default="REORDER", description="추천 유형 (NEW_PRODUCT, REORDER, ALTERNATIVE)")


class RecommendationOut(BaseModel):
    """소싱 추천 결과 모델"""
    id: str
    product_id: Optional[str]
    product_name: Optional[str]
    recommendation_type: str
    recommendation_date: str
    overall_score: float
    sales_potential_score: float
    market_trend_score: float
    profit_margin_score: float
    supplier_reliability_score: float
    seasonal_score: float
    recommended_quantity: int
    min_quantity: int
    max_quantity: int
    current_supply_price: int
    recommended_selling_price: int
    expected_margin: float
    current_stock: int
    stock_days_left: Optional[int]
    reorder_point: int
    reasoning: Optional[str]
    risk_factors: Optional[List[str]]
    opportunity_factors: Optional[List[str]]
    option_recommendations: Optional[List[dict]] = None
    status: str
    confidence_level: float
    created_at: str


class RecommendationActionIn(BaseModel):
    """추천 액션 요청 모델"""
    action_taken: str = Field(..., description="수행된 액션 (예: ORDER_PLACED, REJECTED)")


class RecommendationSummaryOut(BaseModel):
    """추천 요약 모델"""
    period_days: int
    total_recommendations: int
    pending: int
    accepted: int
    rejected: int
    acceptance_rate: float
    avg_overall_score: float

class ScalingRecommendationOut(BaseModel):
    """다채널 확장 추천 모델"""
    product_id: str
    product_name: str
    current_orders: int
    source_market: str
    target_market: str
    expected_impact: str
    difficulty_score: str
    potential_revenue: int
    reason: str


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/generate", response_model=RecommendationOut)
async def generate_recommendation(
    payload: GenerateRecommendationIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """
    제품별 소싱 추천을 생성합니다.
    
    AI 기반 판매 데이터 분석, 시장 트렌드, 재고 상태를 종합적으로 분석하여
    소싱 추천을 제공합니다.
    """
    service = SourcingRecommendationService(session)
    
    try:
        recommendation = await service.generate_product_recommendation(
            product_id=payload.product_id,
            recommendation_type=payload.recommendation_type
        )
        
        return _recommendation_to_response(recommendation, session)
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating recommendation: {e}")
        raise HTTPException(status_code=500, detail="소싱 추천 생성 중 오류가 발생했습니다")


@router.post("/generate/{product_id}", response_model=RecommendationOut)
async def generate_recommendation_by_id(
    product_id: uuid.UUID,
    recommendation_type: str = Query(default="REORDER", description="추천 유형"),
    session: Session = Depends(get_session)
):
    """
    제품 ID로 소싱 추천을 생성합니다.
    """
    service = SourcingRecommendationService(session)
    
    try:
        recommendation = await service.generate_product_recommendation(
            product_id=product_id,
            recommendation_type=recommendation_type
        )
        
        return _recommendation_to_response(recommendation, session)
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating recommendation: {e}")
        raise HTTPException(status_code=500, detail="소싱 추천 생성 중 오류가 발생했습니다")


@router.get("/pending", response_model=List[RecommendationOut])
async def get_pending_recommendations(
    limit: int = Query(default=20, ge=1, le=100, description="조회할 추천 수"),
    session: Session = Depends(get_session)
):
    """
    대기 중인 소싱 추천 목록을 조회합니다.
    
    점수 기준 내림차순 정렬됩니다.
    """
    service = SourcingRecommendationService(session)
    recommendations = service.get_pending_recommendations(limit=limit)
    
    return [
        RecommendationOut(**r)
        for r in recommendations
    ]


@router.get("/summary", response_model=RecommendationSummaryOut)
async def get_recommendation_summary(
    days: int = Query(default=7, ge=1, le=365, description="조회할 일수"),
    session: Session = Depends(get_session)
):
    """
    소싱 추천 요약 통계를 조회합니다.
    
    지정된 기간 동안의 추천 생성 및 수락/거부 현황을 제공합니다.
    """
    service = SourcingRecommendationService(session)
    summary = service.get_recommendation_summary(days=days)
    
    return RecommendationSummaryOut(**summary)


@router.get("/high-priority")
async def get_high_priority_recommendations(
    limit: int = Query(default=10, ge=1, le=50, description="조회할 추천 수"),
    min_score: float = Query(default=70.0, ge=0, le=100, description="최소 점수"),
    session: Session = Depends(get_session)
):
    """
    높은 우선순위의 소싱 추천을 조회합니다.
    
    지정된 최소 점수 이상의 대기 중 추천을 반환합니다.
    """
    from sqlalchemy import select
    
    recommendations = (
        session.execute(
            select(SourcingRecommendation)
            .where(SourcingRecommendation.status == "PENDING")
            .where(SourcingRecommendation.overall_score >= min_score)
            .order_by(SourcingRecommendation.overall_score.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    
    return [
        _recommendation_to_response(r, session)
        for r in recommendations
    ]


@router.get("/reorder-alerts")
async def get_reorder_alerts(
    session: Session = Depends(get_session)
):
    """
    재주문 필요 제품 알림을 조회합니다.
    
    재고가 부족하거나 재주문 시점에 도달한 제품의 추천을 반환합니다.
    """
    from sqlalchemy import select
    
    # 재고 일수가 7일 이하인 추천 조회
    recommendations = (
        session.query(SourcingRecommendation)
        .filter(SourcingRecommendation.status == "PENDING")
        .filter(SourcingRecommendation.stock_days_left.isnot(None))
        .filter(SourcingRecommendation.stock_days_left <= 7)
        .order_by(SourcingRecommendation.stock_days_left.asc())
        .all()
    )
    
    alerts = []
    for r in recommendations:
        product = session.get(Product, r.product_id) if r.product_id else None
        
        # 옵션 중 재고가 매우 적은 것들 카운트
        critical_options_count = 0
        if r.option_recommendations:
            critical_options_count = sum(1 for opt in r.option_recommendations if opt.get('recommended_quantity', 0) > 0)

        alerts.append({
            "recommendation_id": str(r.id),
            "product_name": product.name if product else "Unknown",
            "stock_days_left": r.stock_days_left,
            "recommended_quantity": r.recommended_quantity,
            "overall_score": r.overall_score,
            "critical_options_count": critical_options_count
        })
        
    return {
        "alert_count": len(alerts),
        "alerts": alerts
    }

@router.get("/scaling", response_model=List[ScalingRecommendationOut])
async def get_scaling_recommendations(
    limit: int = Query(default=10, ge=1, le=50),
    session: Session = Depends(get_session)
):
    """
    다채널 확장을 위한 우대 상품 추천 목록을 조회합니다.
    """
    service = SourcingRecommendationService(session)
    return await service.get_scaling_recommendations(limit=limit)


@router.get("/{recommendation_id}", response_model=RecommendationOut)
async def get_recommendation(
    recommendation_id: uuid.UUID,
    session: Session = Depends(get_session)
):
    """
    특정 소싱 추천을 조회합니다.
    """
    recommendation = session.get(SourcingRecommendation, recommendation_id)
    
    if not recommendation:
        raise HTTPException(status_code=404, detail="소싱 추천을 찾을 수 없습니다")
    
    return _recommendation_to_response(recommendation, session)


@router.get("/product/{product_id}")
async def get_product_recommendations(
    product_id: uuid.UUID,
    status: Optional[str] = Query(default=None, description="상태 필터 (PENDING, ACCEPTED, REJECTED)"),
    limit: int = Query(default=10, ge=1, le=50, description="조회할 추천 수"),
    session: Session = Depends(get_session)
):
    """
    제품별 소싱 추천 목록을 조회합니다.
    """
    from sqlalchemy import select
    from app.models import Product
    
    # 제품 존재 확인
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="제품을 찾을 수 없습니다")
    
    # 추천 조회
    stmt = select(SourcingRecommendation).where(
        SourcingRecommendation.product_id == product_id
    )
    
    if status:
        stmt = stmt.where(SourcingRecommendation.status == status)
    
    stmt = stmt.order_by(SourcingRecommendation.created_at.desc()).limit(limit)
    
    recommendations = session.scalars(stmt).all()
    
    return {
        "product_id": str(product_id),
        "product_name": product.name,
        "recommendations": [
            _recommendation_to_response(r, session)
            for r in recommendations
        ]
    }


@router.patch("/{recommendation_id}/accept", response_model=RecommendationOut)
async def accept_recommendation(
    recommendation_id: uuid.UUID,
    payload: RecommendationActionIn,
    session: Session = Depends(get_session)
):
    """
    소싱 추천을 수락합니다.
    
    추천 상태를 ACCEPTED로 변경하고 액션을 기록합니다.
    """
    service = SourcingRecommendationService(session)
    
    try:
        recommendation = service.accept_recommendation(
            recommendation_id=recommendation_id,
            action_taken=payload.action_taken
        )
        
        return _recommendation_to_response(recommendation, session)
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error accepting recommendation: {e}")
        raise HTTPException(status_code=500, detail="추천 수락 중 오류가 발생했습니다")


@router.patch("/{recommendation_id}/reject", response_model=RecommendationOut)
async def reject_recommendation(
    recommendation_id: uuid.UUID,
    payload: RecommendationActionIn,
    session: Session = Depends(get_session)
):
    """
    소싱 추천을 거부합니다.
    
    추천 상태를 REJECTED로 변경하고 액션을 기록합니다.
    """
    service = SourcingRecommendationService(session)
    
    try:
        recommendation = service.reject_recommendation(
            recommendation_id=recommendation_id,
            action_taken=payload.action_taken
        )
        
        return _recommendation_to_response(recommendation, session)
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error rejecting recommendation: {e}")
        raise HTTPException(status_code=500, detail="추천 거부 중 오류가 발생했습니다")


@router.post("/bulk-generate")
async def trigger_bulk_recommendations(
    background_tasks: BackgroundTasks,
    limit: int = Query(default=50, ge=1, le=500, description="생성할 추천 수"),
    recommendation_type: str = Query(default="REORDER", description="추천 유형"),
    session: Session = Depends(get_session)
):
    """
    대량 소싱 추천을 백그라운드에서 실행합니다.
    
    활성 제품들의 소싱 추천을 일괄 생성합니다.
    """
    # 백그라운드 작업 등록
    background_tasks.add_task(
        _execute_bulk_recommendations,
        limit,
        recommendation_type,
        session
    )
    
    return {
        "status": "started",
        "message": f"{limit}개 제품의 소싱 추천 생성을 시작했습니다",
        "limit": limit,
        "recommendation_type": recommendation_type
    }


# ============================================================================
# Helper Functions
# ============================================================================

def _recommendation_to_response(
    recommendation: SourcingRecommendation,
    session: Session
) -> RecommendationOut:
    """SourcingRecommendation 모델을 응답 모델로 변환"""
    product_name = None
    if recommendation.product_id:
        from app.models import Product
        product = session.get(Product, recommendation.product_id)
        product_name = product.name if product else None
    
    return RecommendationOut(
        id=str(recommendation.id),
        product_id=str(recommendation.product_id) if recommendation.product_id else None,
        product_name=product_name,
        recommendation_type=recommendation.recommendation_type,
        recommendation_date=recommendation.recommendation_date.isoformat() if recommendation.recommendation_date else None,
        overall_score=recommendation.overall_score,
        sales_potential_score=recommendation.sales_potential_score,
        market_trend_score=recommendation.market_trend_score,
        profit_margin_score=recommendation.profit_margin_score,
        supplier_reliability_score=recommendation.supplier_reliability_score,
        seasonal_score=recommendation.seasonal_score,
        recommended_quantity=recommendation.recommended_quantity,
        min_quantity=recommendation.min_quantity,
        max_quantity=recommendation.max_quantity,
        current_supply_price=recommendation.current_supply_price,
        recommended_selling_price=recommendation.recommended_selling_price,
        expected_margin=recommendation.expected_margin,
        current_stock=recommendation.current_stock,
        stock_days_left=recommendation.stock_days_left,
        reorder_point=recommendation.reorder_point,
        reasoning=recommendation.reasoning,
        risk_factors=recommendation.risk_factors or [],
        opportunity_factors=recommendation.opportunity_factors or [],
        option_recommendations=recommendation.option_recommendations,
        status=recommendation.status,
        confidence_level=recommendation.confidence_level,
        created_at=recommendation.created_at.isoformat() if recommendation.created_at else None
    )


async def _execute_bulk_recommendations(
    limit: int,
    recommendation_type: str,
    session: Session
):
    """
    대량 소싱 추천 실행 (백그라운드 작업)
    
    Args:
        limit: 생성할 추천 수
        recommendation_type: 추천 유형
        session: 데이터베이스 세션
    """
    from app.session_factory import session_factory
    
    try:
        with session_factory() as db:
            service = SourcingRecommendationService(db)
            recommendations = await service.generate_bulk_recommendations(
                limit=limit,
                recommendation_type=recommendation_type
            )
            
        logger.info(
            f"Bulk recommendations completed: {len(recommendations)} generated"
        )
    except Exception as e:
        logger.error(f"Error in bulk recommendations: {e}")
