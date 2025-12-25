"""
가공 이력 서비스

상품 가공 이력을 추적하고, 가공 전/후의 성과 변화를 분석하여
자체 드랍쉬핑 모델을 구축합니다.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy import select, func
from sqlalchemy.orm import Session
import uuid

from app.models import Product, ProcessingHistory, MarketListing, OrderItem, Order

logger = logging.getLogger(__name__)


class ProcessingHistoryService:
    """
    상품 가공 이력 관리 서비스
    
    가공 유형:
    - NAME: 상품명 가공
    - OPTION: 옵션명 가공
    - DESCRIPTION: 상세 설명 가공
    - IMAGE: 이미지 가공
    - DETAIL_PAGE: 상세페이지 가공
    - FULL_BRANDING: 완전 브랜딩 (이미지+상세페이지 포함)
    """

    # 가공 ROI 계산 기준
    ROI_WEIGHTS = {
        "ctr": 0.3,          # CTR 개선 가중치
        "conversion": 0.4,    # 전환율 개선 가중치
        "sales": 0.2,         # 판매량 개선 가중치
        "cost": 0.1,          # 비용 효율성 가중치
    }

    def __init__(self, db: Session):
        self.db = db

    def record_processing(
        self,
        product_id: uuid.UUID,
        processing_type: str,
        before_data: Dict[str, any],
        after_data: Dict[str, any],
        ai_model: str,
        ai_processing_time_ms: Optional[int] = None,
        ai_cost_estimate: Optional[float] = None
    ) -> ProcessingHistory:
        """
        가공 이력 기록
        
        Args:
            product_id: 상품 ID
            processing_type: 가공 유형 (NAME, OPTION, DESCRIPTION, IMAGE, DETAIL_PAGE, FULL_BRANDING)
            before_data: 가공 전 상태 (name, description, image_urls, etc.)
            after_data: 가공 후 상태
            ai_model: 사용된 AI 모델
            ai_processing_time_ms: AI 처리 시간 (ms)
            ai_cost_estimate: 추정 AI 처리 비용
            
        Returns:
            ProcessingHistory 객체
        """
        product = self.db.get(Product, product_id)
        if not product:
            raise ValueError(f"Product not found: {product_id}")

        # 가공 전 KPI 스냅샷
        before_kpi = self._get_current_kpi(product_id)

        # 가공 이력 생성
        processing = ProcessingHistory(
            product_id=product_id,
            processing_type=processing_type,
            processing_stage=product.lifecycle_stage,
            before_data=before_data,
            before_kpi=before_kpi,
            after_data=after_data,
            ai_model=ai_model,
            ai_processing_time_ms=ai_processing_time_ms,
            ai_cost_estimate=ai_cost_estimate,
            processed_at=datetime.now()
        )

        # 상품의 마지막 가공 정보 업데이트
        product.last_processing_type = processing_type
        product.last_processing_at = datetime.now()
        product.ai_model_used = ai_model

        self.db.add(processing)
        self.db.commit()
        self.db.refresh(processing)

        logger.info(f"Recorded processing history for product {product_id}: "
                   f"type={processing_type}, model={ai_model}")

        return processing

    def measure_processing_impact(
        self,
        processing_history_id: uuid.UUID,
        days_after: int = 7
    ) -> Dict[str, any]:
        """
        가공 영향 측정 (가공 후 N일간의 KPI 변화)
        
        Args:
            processing_history_id: 가공 이력 ID
            days_after: 가공 후 측정 기간 (일)
            
        Returns:
            {
                "before_kpi": {...},
                "after_kpi": {...},
                "improvement": {
                    "ctr": {"value": 0.02, "change": "+133%"},
                    "conversion_rate": {"value": 0.045, "change": "+125%"},
                    "sales": {"value": 10, "change": "+50%"},
                    ...
                },
                "roi_score": 85.5,
                "days_measured": 7
            }
        """
        processing = self.db.get(ProcessingHistory, processing_history_id)
        if not processing:
            raise ValueError(f"Processing history not found: {processing_history_id}")

        if processing.after_kpi:
            # 이미 측정된 경우 기존 데이터 반환
            return {
                "before_kpi": processing.before_kpi,
                "after_kpi": processing.after_kpi,
                "improvement": processing.kpi_improvement,
                "roi_score": processing.roi_score,
                "days_measured": days_after
            }

        # 가공 후 KPI 측정
        after_kpi = self._get_kpi_at_date(
            processing.product_id,
            processing.processed_at + timedelta(days=days_after)
        )

        # 개선율 계산
        improvement = self._calculate_improvement(processing.before_kpi, after_kpi)

        # ROI 점수 계산
        roi_score = self._calculate_roi_score(
            improvement,
            processing.ai_cost_estimate or 0
        )

        # 가공 이력 업데이트
        processing.after_kpi = after_kpi
        processing.kpi_improvement = improvement
        processing.roi_score = roi_score
        processing.kpi_measured_at = datetime.now()

        self.db.commit()

        logger.info(f"Measured processing impact for history {processing_history_id}: "
                   f"roi_score={roi_score:.1f}")

        return {
            "before_kpi": processing.before_kpi,
            "after_kpi": after_kpi,
            "improvement": improvement,
            "roi_score": roi_score,
            "days_measured": days_after
        }

    def get_processing_histories(
        self,
        product_id: uuid.UUID,
        processing_type: Optional[str] = None,
        limit: int = 50
    ) -> List[ProcessingHistory]:
        """
        상품 가공 이력 조회
        
        Args:
            product_id: 상품 ID
            processing_type: 가공 유형 필터 (None = 전체)
            limit: 최대 반환 개수
            
        Returns:
            ProcessingHistory 리스트 (최신순)
        """
        stmt = (
            select(ProcessingHistory)
            .where(ProcessingHistory.product_id == product_id)
        )

        if processing_type:
            stmt = stmt.where(ProcessingHistory.processing_type == processing_type)

        stmt = stmt.order_by(ProcessingHistory.processed_at.desc()).limit(limit)

        return list(self.db.execute(stmt).scalars().all())

    def get_best_practices(
        self,
        processing_type: Optional[str] = None,
        min_roi_score: float = 70.0,
        limit: int = 20
    ) -> List[Dict[str, any]]:
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
        stmt = (
            select(ProcessingHistory)
            .where(ProcessingHistory.roi_score.isnot(None))
            .where(ProcessingHistory.roi_score >= min_roi_score)
        )

        if processing_type:
            stmt = stmt.where(ProcessingHistory.processing_type == processing_type)

        stmt = stmt.order_by(ProcessingHistory.roi_score.desc()).limit(limit)

        results = list(self.db.execute(stmt).scalars().all())

        best_practices = []
        for processing in results:
            product = self.db.get(Product, processing.product_id)

            best_practices.append({
                "product_id": str(processing.product_id),
                "product_name": product.name if product else "Unknown",
                "processing_type": processing.processing_type,
                "processing_stage": processing.processing_stage,
                "ai_model": processing.ai_model,
                "ai_processing_time_ms": processing.ai_processing_time_ms,
                "ai_cost_estimate": processing.ai_cost_estimate,
                "roi_score": processing.roi_score,
                "kpi_improvement": processing.kpi_improvement,
                "processed_at": processing.processed_at.isoformat() if processing.processed_at else None,
                "before_data_example": self._get_summary_data(processing.before_data),
                "after_data_example": self._get_summary_data(processing.after_data)
            })

        return best_practices

    def get_processing_stats(
        self,
        product_id: Optional[uuid.UUID] = None,
        processing_type: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, any]:
        """
        가공 통계 조회
        
        Args:
            product_id: 상품 ID (None = 전체)
            processing_type: 가공 유형 (None = 전체)
            days: 조회 기간 (일)
            
        Returns:
            가공 통계
        """
        since_date = datetime.now() - timedelta(days=days)

        stmt = select(ProcessingHistory).where(
            ProcessingHistory.processed_at >= since_date
        )

        if product_id:
            stmt = stmt.where(ProcessingHistory.product_id == product_id)

        if processing_type:
            stmt = stmt.where(ProcessingHistory.processing_type == processing_type)

        results = list(self.db.execute(stmt).scalars().all())

        if not results:
            return {
                "total_count": 0,
                "total_cost": 0,
                "avg_roi_score": 0,
                "by_type": {},
                "by_stage": {},
                "by_model": {}
            }

        total_count = len(results)
        total_cost = sum(p.ai_cost_estimate or 0 for p in results)
        avg_roi_score = sum(p.roi_score or 0 for p in results) / total_count

        # 유형별 통계
        by_type = {}
        for processing in results:
            ptype = processing.processing_type
            if ptype not in by_type:
                by_type[ptype] = {"count": 0, "avg_roi": 0}
            by_type[ptype]["count"] += 1
            by_type[ptype]["avg_roi"] = (
                (by_type[ptype]["avg_roi"] * (by_type[ptype]["count"] - 1) + (processing.roi_score or 0))
                / by_type[ptype]["count"]
            )

        # 단계별 통계
        by_stage = {}
        for processing in results:
            stage = processing.processing_stage
            if stage not in by_stage:
                by_stage[stage] = {"count": 0, "avg_roi": 0}
            by_stage[stage]["count"] += 1
            by_stage[stage]["avg_roi"] = (
                (by_stage[stage]["avg_roi"] * (by_stage[stage]["count"] - 1) + (processing.roi_score or 0))
                / by_stage[stage]["count"]
            )

        # 모델별 통계
        by_model = {}
        for processing in results:
            model = processing.ai_model or "unknown"
            if model not in by_model:
                by_model[model] = {"count": 0, "avg_roi": 0, "avg_cost": 0, "avg_time_ms": 0}
            by_model[model]["count"] += 1
            by_model[model]["avg_roi"] = (
                (by_model[model]["avg_roi"] * (by_model[model]["count"] - 1) + (processing.roi_score or 0))
                / by_model[model]["count"]
            )
            by_model[model]["avg_cost"] = (
                (by_model[model]["avg_cost"] * (by_model[model]["count"] - 1) + (processing.ai_cost_estimate or 0))
                / by_model[model]["count"]
            )
            by_model[model]["avg_time_ms"] = (
                (by_model[model]["avg_time_ms"] * (by_model[model]["count"] - 1) + (processing.ai_processing_time_ms or 0))
                / by_model[model]["count"]
            )

        return {
            "total_count": total_count,
            "total_cost": total_cost,
            "avg_roi_score": avg_roi_score,
            "by_type": by_type,
            "by_stage": by_stage,
            "by_model": by_model
        }

    def compare_processing_methods(
        self,
        processing_type: str,
        limit: int = 10
    ) -> Dict[str, any]:
        """
        가공 방법별 성과 비교
        
        동일한 가공 유형에 대해 다른 방법(AI 모델, 접근법 등)의 성과를 비교합니다.
        
        Args:
            processing_type: 가공 유형
            limit: 최소 비교 샘플 수
            
        Returns:
            {
                "processing_type": "NAME",
                "methods": [
                    {
                        "ai_model": "qwen3:8b",
                        "count": 50,
                        "avg_roi_score": 85.3,
                        "avg_cost": 0.05,
                        "avg_time_ms": 1200
                    },
                    ...
                ],
                "best_method": {...}
            }
        """
        stmt = (
            select(ProcessingHistory)
            .where(ProcessingHistory.processing_type == processing_type)
            .where(ProcessingHistory.roi_score.isnot(None))
        )

        results = list(self.db.execute(stmt).scalars().all())

        if not results:
            return {
                "processing_type": processing_type,
                "methods": [],
                "best_method": None
            }

        # 모델별 집계
        methods = {}
        for processing in results:
            model = processing.ai_model or "unknown"
            if model not in methods:
                methods[model] = {
                    "ai_model": model,
                    "count": 0,
                    "total_roi": 0,
                    "total_cost": 0,
                    "total_time_ms": 0
                }
            methods[model]["count"] += 1
            methods[model]["total_roi"] += processing.roi_score or 0
            methods[model]["total_cost"] += processing.ai_cost_estimate or 0
            methods[model]["total_time_ms"] += processing.ai_processing_time_ms or 0

        # 평균 계산 및 필터링
        method_list = []
        for model, stats in methods.items():
            if stats["count"] >= limit:
                method_list.append({
                    "ai_model": model,
                    "count": stats["count"],
                    "avg_roi_score": stats["total_roi"] / stats["count"],
                    "avg_cost": stats["total_cost"] / stats["count"],
                    "avg_time_ms": stats["total_time_ms"] / stats["count"]
                })

        # ROI 기준 정렬
        method_list.sort(key=lambda x: x["avg_roi_score"], reverse=True)

        best_method = method_list[0] if method_list else None

        return {
            "processing_type": processing_type,
            "methods": method_list,
            "best_method": best_method
        }

    # ==================== 내부 헬퍼 메서드 ====================

    def _get_current_kpi(self, product_id: uuid.UUID) -> Dict[str, any]:
        """현재 상품 KPI 조회"""
        product = self.db.get(Product, product_id)
        if not product:
            return {}

        return {
            "total_views": product.total_views,
            "total_clicks": product.total_clicks,
            "total_sales_count": product.total_sales_count,
            "total_revenue": product.total_revenue,
            "ctr": product.ctr,
            "conversion_rate": product.conversion_rate,
            "avg_customer_value": product.avg_customer_value,
            "repeat_purchase_count": product.repeat_purchase_count,
            "customer_retention_rate": product.customer_retention_rate
        }

    def _get_kpi_at_date(self, product_id: uuid.UUID, target_date: datetime) -> Dict[str, any]:
        """
        특정 날짜 시점의 KPI 조회
        
        Order 데이터의 created_at을 기준으로 집계합니다.
        """
        # 해당 날짜까지의 주문 데이터만 집계
        sales_stmt = (
            select(
                func.sum(OrderItem.quantity).label("total_sales_count"),
                func.sum(OrderItem.quantity * OrderItem.unit_price).label("total_revenue"),
                func.count(func.distinct(Order.customer_id)).label("unique_customers")
            )
            .join(Order, OrderItem.order_id == Order.id)
            .where(OrderItem.product_id == product_id)
            .where(Order.created_at <= target_date)
        )

        sales_result = self.db.execute(sales_stmt).one_or_none()
        total_sales_count = sales_result.total_sales_count or 0 if sales_result else 0
        total_revenue = int(sales_result.total_revenue or 0) if sales_result else 0
        unique_customers = sales_result.unique_customers or 0 if sales_result else 0

        # 노출/클릭 데이터는 현재 값을 사용 (시계열 데이터가 없는 경우)
        product = self.db.get(Product, product_id)
        if product:
            total_views = product.total_views
            total_clicks = product.total_clicks
            ctr = product.ctr
            conversion_rate = product.conversion_rate
            avg_customer_value = product.avg_customer_value
            repeat_purchase_count = product.repeat_purchase_count
            customer_retention_rate = product.customer_retention_rate
        else:
            total_views = 0
            total_clicks = 0
            ctr = 0.0
            conversion_rate = 0.0
            avg_customer_value = 0.0
            repeat_purchase_count = 0
            customer_retention_rate = 0.0

        return {
            "total_views": total_views,
            "total_clicks": total_clicks,
            "total_sales_count": total_sales_count,
            "total_revenue": total_revenue,
            "ctr": ctr,
            "conversion_rate": conversion_rate,
            "avg_customer_value": avg_customer_value,
            "repeat_purchase_count": repeat_purchase_count,
            "customer_retention_rate": customer_retention_rate
        }

    def _calculate_improvement(
        self,
        before_kpi: Dict[str, any],
        after_kpi: Dict[str, any]
    ) -> Dict[str, any]:
        """
        KPI 개선율 계산
        
        Returns:
            {
                "ctr": {"value": 0.035, "change": "+133%"},
                "conversion_rate": {"value": 0.045, "change": "+125%"},
                "total_sales_count": {"value": 10, "change": "+50%"},
                "total_revenue": {"value": 50000, "change": "+75%"}
            }
        """
        improvement = {}

        # CTR 개선율
        if "ctr" in before_kpi and "ctr" in after_kpi:
            before_ctr = before_kpi["ctr"]
            after_ctr = after_kpi["ctr"]
            if before_ctr > 0:
                ctr_change = (after_ctr - before_ctr) / before_ctr
                improvement["ctr"] = {
                    "value": after_ctr,
                    "change": f"+{ctr_change * 100:.1f}%" if ctr_change > 0 else f"{ctr_change * 100:.1f}%"
                }

        # 전환율 개선율
        if "conversion_rate" in before_kpi and "conversion_rate" in after_kpi:
            before_conv = before_kpi["conversion_rate"]
            after_conv = after_kpi["conversion_rate"]
            if before_conv > 0:
                conv_change = (after_conv - before_conv) / before_conv
                improvement["conversion_rate"] = {
                    "value": after_conv,
                    "change": f"+{conv_change * 100:.1f}%" if conv_change > 0 else f"{conv_change * 100:.1f}%"
                }

        # 판매량 개선율
        if "total_sales_count" in before_kpi and "total_sales_count" in after_kpi:
            before_sales = before_kpi["total_sales_count"]
            after_sales = after_kpi["total_sales_count"]
            if before_sales > 0:
                sales_change = (after_sales - before_sales) / before_sales
                improvement["total_sales_count"] = {
                    "value": after_sales,
                    "change": f"+{sales_change * 100:.1f}%" if sales_change > 0 else f"{sales_change * 100:.1f}%"
                }

        # 매출 개선율
        if "total_revenue" in before_kpi and "total_revenue" in after_kpi:
            before_rev = before_kpi["total_revenue"]
            after_rev = after_kpi["total_revenue"]
            if before_rev > 0:
                rev_change = (after_rev - before_rev) / before_rev
                improvement["total_revenue"] = {
                    "value": after_rev,
                    "change": f"+{rev_change * 100:.1f}%" if rev_change > 0 else f"{rev_change * 100:.1f}%"
                }

        return improvement

    def _calculate_roi_score(
        self,
        improvement: Dict[str, any],
        ai_cost: float
    ) -> float:
        """
        ROI 점수 계산 (0-100)
        
        KPI 개선율과 AI 비용을 종합하여 ROI 점수를 계산합니다.
        """
        score = 0.0

        # CTR 개선 점수 (0-30점)
        if "ctr" in improvement:
            ctr_change_str = improvement["ctr"]["change"].replace("%", "")
            ctr_change = float(ctr_change_str)
            ctr_score = min(30, max(0, ctr_change * 3))  # 10% 개선 시 30점
            score += ctr_score * self.ROI_WEIGHTS["ctr"]

        # 전환율 개선 점수 (0-40점)
        if "conversion_rate" in improvement:
            conv_change_str = improvement["conversion_rate"]["change"].replace("%", "")
            conv_change = float(conv_change_str)
            conv_score = min(40, max(0, conv_change * 2))  # 20% 개선 시 40점
            score += conv_score * self.ROI_WEIGHTS["conversion"]

        # 판매량 개선 점수 (0-20점)
        if "total_sales_count" in improvement:
            sales_change_str = improvement["total_sales_count"]["change"].replace("%", "")
            sales_change = float(sales_change_str)
            sales_score = min(20, max(0, sales_change * 1))  # 20% 개선 시 20점
            score += sales_score * self.ROI_WEIGHTS["sales"]

        # 비용 효율성 점수 (0-10점)
        # AI 비용이 0이면 최고점, 높으면 감점
        if ai_cost == 0:
            cost_score = 10
        elif ai_cost < 0.1:
            cost_score = 8
        elif ai_cost < 1:
            cost_score = 5
        else:
            cost_score = 2
        score += cost_score * self.ROI_WEIGHTS["cost"]

        return round(score, 1)

    def _get_summary_data(self, data: Dict[str, any]) -> Dict[str, any]:
        """데이터 요약 (로그 출력용)"""
        summary = {}

        if "name" in data:
            summary["name"] = data["name"]

        if "description" in data:
            desc = data["description"]
            if isinstance(desc, str) and len(desc) > 100:
                summary["description"] = desc[:100] + "..."
            else:
                summary["description"] = desc

        if "image_urls" in data:
            summary["image_count"] = len(data["image_urls"]) if isinstance(data["image_urls"], list) else 0

        return summary
