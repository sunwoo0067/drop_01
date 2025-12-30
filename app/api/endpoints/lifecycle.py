"""
상품 라이프사이클 API 엔드포인트

3단계 드랍쉬핑 전략 (탐색 → 검증 → 스케일)을 위한 API를 제공합니다.
"""

import logging
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_session
from app.services.product_lifecycle_service import ProductLifecycleService
from app.services.processing_history_service import ProcessingHistoryService

router = APIRouter()
logger = logging.getLogger(__name__)


# ==================== Request/Response Models ====================

class TransitionRequest(BaseModel):
    """단계 전환 요청"""
    reason: Optional[str] = Field(default="", description="전환 사유")
    auto_transition: bool = Field(default=False, description="자동 전환 여부")


class TransitionEligibilityResponse(BaseModel):
    """전환 가능 여부 응답"""
    eligible: bool
    current_stage: str
    next_stage: Optional[str]
    criteria: dict
    category_label: str
    criteria_met: dict
    missing_criteria: List[str]
    kpi_snapshot: dict


class ProductLifecycleHistoryResponse(BaseModel):
    """상품 라이프사이클 이력 응답"""
    id: str
    product_id: str
    transition_sequence: int
    from_stage: Optional[str]
    to_stage: str
    kpi_snapshot: dict
    transition_reason: Optional[str]
    auto_transition: bool
    created_at: str


class ProcessingStatsResponse(BaseModel):
    """가공 통계 응답"""
    total_count: int
    total_cost: float
    avg_roi_score: float
    by_type: dict
    by_stage: dict
    by_model: dict


# ==================== 단계 전환 관련 엔드포인트 ====================

@router.get("/products/{product_id}/lifecycle", response_model=dict)
async def get_product_lifecycle(
    product_id: uuid.UUID,
    include_history: bool = Query(default=True),
    session: Session = Depends(get_session)
):
    """
    상품 라이프사이클 정보 조회
    
    Args:
        product_id: 상품 ID
        include_history: 이력 포함 여부
        
    Returns:
        {
            "product": {...},
            "eligibility": {...},
            "history": [...]
        }
    """
    from app.models import Product
    
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"상품을 찾을 수 없습니다: {product_id}")

    lifecycle_service = ProductLifecycleService(session)

    # 전환 가능 여부 확인
    eligibility = lifecycle_service.check_transition_eligibility(product_id)

    # 이력 조회
    history = []
    if include_history:
        history_records = lifecycle_service.get_lifecycle_history(product_id)
        history = [
            {
                "id": str(h.id),
                "product_id": str(h.product_id),
                "transition_sequence": h.transition_sequence,
                "from_stage": h.from_stage,
                "to_stage": h.to_stage,
                "kpi_snapshot": h.kpi_snapshot,
                "transition_reason": h.transition_reason,
                "auto_transition": h.auto_transition,
                "created_at": h.created_at.isoformat() if h.created_at else None
            }
            for h in history_records
        ]

    return {
        "product": {
            "id": str(product.id),
            "name": product.name,
            "lifecycle_stage": product.lifecycle_stage,
            "lifecycle_stage_updated_at": product.lifecycle_stage_updated_at.isoformat() if product.lifecycle_stage_updated_at else None,
            "total_sales_count": product.total_sales_count,
            "total_views": product.total_views,
            "total_clicks": product.total_clicks,
            "ctr": product.ctr,
            "conversion_rate": product.conversion_rate,
            "total_revenue": product.total_revenue
        },
        "eligibility": eligibility,
        "history": history
    }


@router.post("/products/{product_id}/lifecycle/transition/step2")
async def transition_to_step2(
    product_id: uuid.UUID,
    request: TransitionRequest,
    session: Session = Depends(get_session)
):
    """
    상품 STEP 2로 전환 (탐색 → 검증)
    
    조건:
    - 판매 ≥ 1
    - CTR ≥ 2%
    - 노출 ≥ 100
    """
    try:
        lifecycle_service = ProductLifecycleService(session)
        lifecycle = lifecycle_service.transition_to_step2(
            product_id=product_id,
            reason=request.reason or "수동 전환",
            auto_transition=request.auto_transition
        )

        return {
            "message": "STEP 2로 전환되었습니다",
            "lifecycle": {
                "id": str(lifecycle.id),
                "from_stage": lifecycle.from_stage,
                "to_stage": lifecycle.to_stage,
                "transition_reason": lifecycle.transition_reason,
                "auto_transition": lifecycle.auto_transition,
                "kpi_snapshot": lifecycle.kpi_snapshot,
                "created_at": lifecycle.created_at.isoformat() if lifecycle.created_at else None
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"STEP 2 전환 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"전환 실패: {str(e)}")


@router.post("/products/{product_id}/lifecycle/transition/step3")
async def transition_to_step3(
    product_id: uuid.UUID,
    request: TransitionRequest,
    session: Session = Depends(get_session)
):
    """
    상품 STEP 3로 전환 (검증 → 스케일)
    
    조건:
    - 판매 ≥ 5
    - 재구매 ≥ 1
    """
    try:
        lifecycle_service = ProductLifecycleService(session)
        lifecycle = lifecycle_service.transition_to_step3(
            product_id=product_id,
            reason=request.reason or "수동 전환",
            auto_transition=request.auto_transition
        )

        return {
            "message": "STEP 3로 전환되었습니다",
            "lifecycle": {
                "id": str(lifecycle.id),
                "from_stage": lifecycle.from_stage,
                "to_stage": lifecycle.to_stage,
                "transition_reason": lifecycle.transition_reason,
                "auto_transition": lifecycle.auto_transition,
                "kpi_snapshot": lifecycle.kpi_snapshot,
                "created_at": lifecycle.created_at.isoformat() if lifecycle.created_at else None
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"STEP 3 전환 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"전환 실패: {str(e)}")


# ==================== 단계별 상품 조회 ====================

@router.get("/products/by-stage/{stage}")
async def get_products_by_stage(
    stage: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session)
):
    """
    단계별 상품 목록 조회
    
    Args:
        stage: "STEP_1", "STEP_2", "STEP_3"
        limit: 최대 반환 개수
        offset: 오프셋
        
    Returns:
        상품 리스트
    """
    try:
        lifecycle_service = ProductLifecycleService(session)
        products = lifecycle_service.get_products_by_stage(stage, limit, offset)

        return {
            "stage": stage,
            "count": len(products),
            "products": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "lifecycle_stage": p.lifecycle_stage,
                    "lifecycle_stage_updated_at": p.lifecycle_stage_updated_at.isoformat() if p.lifecycle_stage_updated_at else None,
                    "total_sales_count": p.total_sales_count,
                    "total_views": p.total_views,
                    "total_clicks": p.total_clicks,
                    "ctr": p.ctr,
                    "conversion_rate": p.conversion_rate,
                    "total_revenue": p.total_revenue,
                    "processing_status": p.processing_status,
                    "status": p.status
                }
                for p in products
            ]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"상품 목록 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")


# ==================== 전환 가능 상품 조회 ====================

@router.get("/lifecycle/candidates")
async def get_transition_candidates(
    stage: str = Query(..., description="STEP_1 또는 STEP_2"),
    session: Session = Depends(get_session)
):
    """
    전환 가능한 상품 목록 조회
    
    지정된 단계에서 다음 단계로 전환 가능한 상품들을 조회합니다.
    
    Args:
        stage: "STEP_1" 또는 "STEP_2"
        
    Returns:
        전환 가능한 상품 리스트
    """
    try:
        lifecycle_service = ProductLifecycleService(session)
        candidates = lifecycle_service.get_transition_candidates(stage)

        return {
            "stage": stage,
            "next_stage": "STEP_2" if stage == "STEP_1" else "STEP_3",
            "candidate_count": len(candidates),
            "candidates": candidates
        }
    except Exception as e:
        logger.error(f"전환 후보 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")


# ==================== 자동 전환 ====================

@router.post("/lifecycle/check-all-transitions")
async def check_all_transitions(
    background_tasks: BackgroundTasks,
    dry_run: bool = Query(default=True, description="실제 전환 여부 (False면 실제 전환 수행)"),
    session: Session = Depends(get_session)
):
    """
    모든 상품의 전환 조건 체크 및 자동 전환
    
    백그라운드 테스크로 실행됩니다.
    
    Args:
        dry_run: True면 전환 조건만 체크, False면 실제 전환 수행
    """
    async def _run_transitions():
        lifecycle_service = ProductLifecycleService(session)
        
        results = {
            "step1_to_step2": {"checked": 0, "transitioned": 0, "candidates": []},
            "step2_to_step3": {"checked": 0, "transitioned": 0, "candidates": []}
        }

        try:
            # STEP 1 → 2 체크
            step1_candidates = lifecycle_service.get_transition_candidates("STEP_1")
            results["step1_to_step2"]["checked"] = len(step1_candidates)
            results["step1_to_step2"]["candidates"] = step1_candidates

            if not dry_run:
                for candidate in step1_candidates:
                    try:
                        lifecycle_service.transition_to_step2(
                            uuid.UUID(candidate["product_id"]),
                            reason="자동 전환",
                            auto_transition=True
                        )
                        results["step1_to_step2"]["transitioned"] += 1
                    except Exception as e:
                        logger.error(f"STEP 1→2 전환 실패 (product={candidate['product_id']}): {e}")

            # STEP 2 → 3 체크
            step2_candidates = lifecycle_service.get_transition_candidates("STEP_2")
            results["step2_to_step3"]["checked"] = len(step2_candidates)
            results["step2_to_step3"]["candidates"] = step2_candidates

            if not dry_run:
                for candidate in step2_candidates:
                    try:
                        lifecycle_service.transition_to_step3(
                            uuid.UUID(candidate["product_id"]),
                            reason="자동 전환",
                            auto_transition=True
                        )
                        results["step2_to_step3"]["transitioned"] += 1
                    except Exception as e:
                        logger.error(f"STEP 2→3 전환 실패 (product={candidate['product_id']}): {e}")

            logger.info(f"전환 체크 완료: {results}")

        except Exception as e:
            logger.error(f"전환 체크 중 오류: {e}", exc_info=True)
            results["error"] = str(e)

        return results

    # 백그라운드 테스크로 실행
    background_tasks.add_task(_run_transitions)

    return {
        "message": "백그라운드에서 전환 조건 체크를 시작합니다",
        "dry_run": dry_run
    }


# ==================== KPI 관련 엔드포인트 ====================

@router.post("/products/{product_id}/kpi/update")
async def update_product_kpi(
    product_id: uuid.UUID,
    session: Session = Depends(get_session)
):
    """
    상품 KPI 업데이트
    
    마켓별 노출/클릭 데이터와 주문 데이터를 집계하여 상품 KPI를 계산합니다.
    """
    try:
        lifecycle_service = ProductLifecycleService(session)
        kpi_data = lifecycle_service.update_product_kpi(product_id)

        return {
            "message": "KPI가 업데이트되었습니다",
            "product_id": str(product_id),
            "kpi": kpi_data
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"KPI 업데이트 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"업데이트 실패: {str(e)}")


# ==================== 가공 이력 관련 엔드포인트 ====================

@router.get("/products/{product_id}/processing-histories")
async def get_processing_histories(
    product_id: uuid.UUID,
    processing_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_session)
):
    """
    상품 가공 이력 조회
    
    Args:
        product_id: 상품 ID
        processing_type: 가공 유형 필터 (None = 전체)
        limit: 최대 반환 개수
        
    Returns:
        가공 이력 리스트
    """
    try:
        from app.models import Product
        
        product = session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"상품을 찾을 수 없습니다: {product_id}")

        history_service = ProcessingHistoryService(session)
        histories = history_service.get_processing_histories(product_id, processing_type, limit)

        return {
            "product_id": str(product_id),
            "count": len(histories),
            "histories": [
                {
                    "id": str(h.id),
                    "product_id": str(h.product_id),
                    "processing_type": h.processing_type,
                    "processing_stage": h.processing_stage,
                    "ai_model": h.ai_model,
                    "ai_processing_time_ms": h.ai_processing_time_ms,
                    "ai_cost_estimate": h.ai_cost_estimate,
                    "roi_score": h.roi_score,
                    "kpi_improvement": h.kpi_improvement,
                    "processed_at": h.processed_at.isoformat() if h.processed_at else None,
                    "kpi_measured_at": h.kpi_measured_at.isoformat() if h.kpi_measured_at else None
                }
                for h in histories
            ]
        }
    except Exception as e:
        logger.error(f"가공 이력 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")


@router.post("/processing-histories/{history_id}/measure-impact")
async def measure_processing_impact(
    history_id: uuid.UUID,
    days_after: int = Query(default=7, ge=1, le=30),
    session: Session = Depends(get_session)
):
    """
    가공 영향 측정
    
    가공 후 N일간의 KPI 변화를 측정합니다.
    
    Args:
        history_id: 가공 이력 ID
        days_after: 가공 후 측정 기간 (일)
    """
    try:
        history_service = ProcessingHistoryService(session)
        impact = history_service.measure_processing_impact(history_id, days_after)

        return {
            "message": "가공 영향이 측정되었습니다",
            "history_id": str(history_id),
            "impact": impact
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"가공 영향 측정 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"측정 실패: {str(e)}")


# ==================== 통계 및 분석 ====================

@router.get("/lifecycle/distribution")
async def get_lifecycle_distribution(session: Session = Depends(get_session)):
    """
    단계별 상품 분포 통계
    
    Returns:
        {
            "STEP_1": 100,
            "STEP_2": 50,
            "STEP_3": 10
        }
    """
    try:
        lifecycle_service = ProductLifecycleService(session)
        distribution = lifecycle_service.get_stage_distribution()

        return {
            "distribution": distribution,
            "total": sum(distribution.values())
        }
    except Exception as e:
        logger.error(f"분포 통계 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")


@router.get("/processing/best-practices")
async def get_best_practices(
    processing_type: Optional[str] = Query(default=None),
    min_roi_score: float = Query(default=70.0, ge=0, le=100),
    limit: int = Query(default=20, ge=1, le=50),
    session: Session = Depends(get_session)
):
    """
    최적 가공 방법 추천
    
    ROI 점수가 높은 가공 이력을 기반으로 최적 사례를 추천합니다.
    
    Args:
        processing_type: 가공 유형 (None = 전체)
        min_roi_score: 최소 ROI 점수
        limit: 최대 반환 개수
        
    Returns:
        최적 사례 리스트
    """
    try:
        history_service = ProcessingHistoryService(session)
        best_practices = history_service.get_best_practices(processing_type, min_roi_score, limit)

        return {
            "processing_type": processing_type or "ALL",
            "min_roi_score": min_roi_score,
            "count": len(best_practices),
            "best_practices": best_practices
        }
    except Exception as e:
        logger.error(f"최적 사례 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")


@router.get("/processing/stats")
async def get_processing_stats(
    product_id: Optional[uuid.UUID] = Query(default=None),
    processing_type: Optional[str] = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    session: Session = Depends(get_session)
):
    """
    가공 통계 조회
    
    Args:
        product_id: 상품 ID (None = 전체)
        processing_type: 가공 유형 (None = 전체)
        days: 조회 기간 (일)
        
    Returns:
        가공 통계
    """
    try:
        history_service = ProcessingHistoryService(session)
        stats = history_service.get_processing_stats(product_id, processing_type, days)

        return {
            "period_days": days,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"가공 통계 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")


@router.get("/processing/compare-methods")
async def compare_processing_methods(
    processing_type: str = Query(...),
    limit: int = Query(default=10, ge=1, le=100),
    session: Session = Depends(get_session)
):
    """
    가공 방법별 성과 비교
    
    동일한 가공 유형에 대해 다른 방법(AI 모델, 접근법 등)의 성과를 비교합니다.
    
    Args:
        processing_type: 가공 유형
        limit: 최소 비교 샘플 수
        
    Returns:
        가공 방법별 성과 비교
    """
    try:
        history_service = ProcessingHistoryService(session)
        comparison = history_service.compare_processing_methods(processing_type, limit)

        return comparison
    except Exception as e:
        logger.error(f"가공 방법 비교 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"비교 실패: {str(e)}")
