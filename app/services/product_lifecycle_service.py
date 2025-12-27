"""
상품 라이프사이클 서비스

3단계 드랍쉬핑 전략 (탐색 → 검증 → 스케일)을 구현합니다.
상품의 성과(KPI)에 따라 자동으로 단계를 전환하고, 가공 레벨을 조정합니다.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy import select, func
from sqlalchemy.orm import Session
import uuid

from app.models import Product, ProductLifecycle, MarketListing, OrderItem, Order

logger = logging.getLogger(__name__)


class ProductLifecycleService:
    """
    상품 라이프사이클 단계 관리 서비스
    
    단계별 전환 조건:
    - STEP 1 → 2: 판매 ≥ 1 AND CTR ≥ 2% AND 노출 ≥ 100
    - STEP 2 → 3: 판매 ≥ 5 AND 재구매 ≥ 1
    """

    # STEP 1 → 2 전환 기준 (탐색 → 검증)
    STEP_1_TO_2_CRITERIA = {
        "min_sales": 1,           # 최소 판매 횟수
        "min_ctr": 0.02,          # 최소 CTR (2%)
        "min_views": 100,         # 최소 노출수
        "min_days_listed": 7,     # 최소 등록 일수
    }

    # STEP 2 → 3 전환 기준 (검증 → 스케일)
    STEP_2_TO_3_CRITERIA = {
        "min_sales": 5,                    # 최소 판매 횟수
        "min_repeat_purchase": 1,          # 최소 재구매 횟수
        "min_customer_retention": 0.1,     # 최소 고객 유지율 (10%)
        "min_revenue": 100000,             # 최소 총 매출 (원)
        "min_days_in_step2": 14,           # STEP 2 최소 체류 일수
    }

    # 카테고리별 전환 기준 조정 (향후 확장 가능)
    CATEGORY_ADJUSTED_CRITERIA = {
        "패션의류": {"min_sales": 3},  # 빠른 회전
        "가전제품": {"min_sales": 7},  # 느린 회전
        "기본": {},
    }

    def __init__(self, db: Session):
        self.db = db

    def check_transition_eligibility(self, product_id: uuid.UUID) -> Dict[str, any]:
        """
        단계 전환 가능 여부 확인
        
        Returns:
            {
                "eligible": bool,
                "current_stage": str,
                "next_stage": Optional[str],
                "criteria_met": Dict[str, any],
                "missing_criteria": List[str],
                "kpi_snapshot": Dict[str, any]
            }
        """
        product = self.db.get(Product, product_id)
        if not product:
            raise ValueError(f"Product not found: {product_id}")

        current_stage = product.lifecycle_stage
        
        # KPI 스냅샷 생성
        kpi_snapshot = self._get_kpi_snapshot(product)
        
        result = {
            "eligible": False,
            "current_stage": current_stage,
            "next_stage": None,
            "criteria_met": {},
            "missing_criteria": [],
            "kpi_snapshot": kpi_snapshot
        }

        if current_stage == "STEP_1":
            result.update(self._check_step1_to_step2(product))
        elif current_stage == "STEP_2":
            result.update(self._check_step2_to_step3(product))
        elif current_stage == "STEP_3":
            result["message"] = "이미 최종 단계입니다"

        return result

    def _check_step1_to_step2(self, product: Product) -> Dict[str, any]:
        """STEP 1 → 2 전환 조건 확인"""
        criteria = self.STEP_1_TO_2_CRITERIA
        criteria_met = {}
        missing_criteria = []

        # 판매 횟수 확인
        sales_count = product.total_sales_count
        if sales_count >= criteria["min_sales"]:
            criteria_met["sales"] = sales_count
        else:
            missing_criteria.append(f"판매 횟수 부족 (현재: {sales_count}, 필요: {criteria['min_sales']})")

        # CTR 확인
        ctr = product.ctr
        if ctr >= criteria["min_ctr"]:
            criteria_met["ctr"] = ctr
        else:
            missing_criteria.append(f"CTR 부족 (현재: {ctr:.1%}, 필요: {criteria['min_ctr']:.1%})")

        # 노출수 확인
        views = product.total_views
        if views >= criteria["min_views"]:
            criteria_met["views"] = views
        else:
            missing_criteria.append(f"노출수 부족 (현재: {views}, 필요: {criteria['min_views']})")

        # 등록 일수 확인
        days_listed = self._get_days_listed(product)
        if days_listed >= criteria["min_days_listed"]:
            criteria_met["days_listed"] = days_listed
        else:
            missing_criteria.append(f"등록 기간 부족 (현재: {days_listed}일, 필요: {criteria['min_days_listed']}일)")

        eligible = len(missing_criteria) == 0

        return {
            "eligible": eligible,
            "next_stage": "STEP_2" if eligible else None,
            "criteria_met": criteria_met,
            "missing_criteria": missing_criteria
        }

    def _check_step2_to_step3(self, product: Product) -> Dict[str, any]:
        """STEP 2 → 3 전환 조건 확인"""
        criteria = self.STEP_2_TO_3_CRITERIA
        criteria_met = {}
        missing_criteria = []

        # 판매 횟수 확인
        sales_count = product.total_sales_count
        if sales_count >= criteria["min_sales"]:
            criteria_met["sales"] = sales_count
        else:
            missing_criteria.append(f"판매 횟수 부족 (현재: {sales_count}, 필요: {criteria['min_sales']})")

        # 재구매 횟수 확인
        repeat_count = product.repeat_purchase_count
        if repeat_count >= criteria["min_repeat_purchase"]:
            criteria_met["repeat_purchase"] = repeat_count
        else:
            missing_criteria.append(f"재구매 횟수 부족 (현재: {repeat_count}, 필요: {criteria['min_repeat_purchase']})")

        # 고객 유지율 확인
        retention_rate = product.customer_retention_rate
        if retention_rate >= criteria["min_customer_retention"]:
            criteria_met["customer_retention_rate"] = retention_rate
        else:
            missing_criteria.append(f"고객 유지율 부족 (현재: {retention_rate:.1%}, 필요: {criteria['min_customer_retention']:.1%})")

        # 총 매출 확인
        total_revenue = product.total_revenue
        if total_revenue >= criteria["min_revenue"]:
            criteria_met["total_revenue"] = total_revenue
        else:
            missing_criteria.append(f"총 매출 부족 (현재: {total_revenue:,}원, 필요: {criteria['min_revenue']:,}원)")

        # STEP 2 체류 일수 확인
        days_in_step2 = self._get_days_in_stage(product, "STEP_2")
        if days_in_step2 >= criteria["min_days_in_step2"]:
            criteria_met["days_in_step2"] = days_in_step2
        else:
            missing_criteria.append(f"STEP 2 체류 기간 부족 (현재: {days_in_step2}일, 필요: {criteria['min_days_in_step2']}일)")

        eligible = len(missing_criteria) == 0

        return {
            "eligible": eligible,
            "next_stage": "STEP_3" if eligible else None,
            "criteria_met": criteria_met,
            "missing_criteria": missing_criteria
        }

    def transition_to_step2(self, product_id: uuid.UUID, reason: str = "", auto_transition: bool = False) -> ProductLifecycle:
        """
        STEP 1 → 2 전환 (탐색 → 검증)
        
        이 단계에서:
        - 상품명·옵션·상세 설명 개선
        - SEO 최적화 (qwen3:8b 사용)
        """
        product = self.db.get(Product, product_id)
        if not product:
            raise ValueError(f"Product not found: {product_id}")

        if product.lifecycle_stage != "STEP_1":
            raise ValueError(f"Current stage is {product.lifecycle_stage}, cannot transition to STEP_2")

        logger.info(f"Transitioning product {product_id} from STEP_1 to STEP_2")

        # KPI 스냅샷 생성
        kpi_snapshot = self._get_kpi_snapshot(product)

        # 라이프사이클 이력 생성
        transition_sequence = self._get_next_transition_sequence(product_id)

        lifecycle = ProductLifecycle(
            product_id=product_id,
            transition_sequence=transition_sequence,
            from_stage="STEP_1",
            to_stage="STEP_2",
            kpi_snapshot=kpi_snapshot,
            transition_reason=reason or "판매 ≥ 1 AND CTR ≥ 2% 기준 충족",
            auto_transition=auto_transition
        )

        # 상품 단계 업데이트
        product.lifecycle_stage = "STEP_2"
        product.lifecycle_stage_updated_at = datetime.now()

        self.db.add(lifecycle)
        self.db.commit()
        self.db.refresh(lifecycle)

        logger.info(f"Product {product_id} transitioned to STEP_2: {reason}")
        return lifecycle

    def transition_to_step3(self, product_id: uuid.UUID, reason: str = "", auto_transition: bool = False) -> ProductLifecycle:
        """
        STEP 2 → 3 전환 (검증 → 스케일)
        
        이 단계에서:
        - 이미지·상세페이지 완전 교체
        - 브랜드 수준 가공 (qwen3-vl:8b + 외부 API)
        """
        product = self.db.get(Product, product_id)
        if not product:
            raise ValueError(f"Product not found: {product_id}")

        if product.lifecycle_stage != "STEP_2":
            raise ValueError(f"Current stage is {product.lifecycle_stage}, cannot transition to STEP_3")

        logger.info(f"Transitioning product {product_id} from STEP_2 to STEP_3")

        # KPI 스냅샷 생성
        kpi_snapshot = self._get_kpi_snapshot(product)

        # 라이프사이클 이력 생성
        transition_sequence = self._get_next_transition_sequence(product_id)

        lifecycle = ProductLifecycle(
            product_id=product_id,
            transition_sequence=transition_sequence,
            from_stage="STEP_2",
            to_stage="STEP_3",
            kpi_snapshot=kpi_snapshot,
            transition_reason=reason or "판매 ≥ 5 AND 재구매 ≥ 1 기준 충족",
            auto_transition=auto_transition
        )

        # 상품 단계 업데이트
        product.lifecycle_stage = "STEP_3"
        product.lifecycle_stage_updated_at = datetime.now()

        self.db.add(lifecycle)
        self.db.commit()
        self.db.refresh(lifecycle)

        logger.info(f"Product {product_id} transitioned to STEP_3: {reason}")
        return lifecycle

    def get_lifecycle_history(self, product_id: uuid.UUID) -> List[ProductLifecycle]:
        """
        상품 라이프사이클 이력 조회
        
        Args:
            product_id: 상품 ID
            
        Returns:
            ProductLifecycle 리스트 (최신순)
        """
        stmt = (
            select(ProductLifecycle)
            .where(ProductLifecycle.product_id == product_id)
            .order_by(ProductLifecycle.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_products_by_stage(
        self,
        stage: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Product]:
        """
        단계별 상품 목록 조회
        
        Args:
            stage: "STEP_1", "STEP_2", "STEP_3"
            limit: 최대 반환 개수
            offset: 오프셋
            
        Returns:
            Product 리스트
        """
        if stage not in ["STEP_1", "STEP_2", "STEP_3"]:
            raise ValueError(f"Invalid stage: {stage}")

        stmt = (
            select(Product)
            .where(Product.lifecycle_stage == stage)
            .order_by(Product.lifecycle_stage_updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.execute(stmt).scalars().all())

    def update_product_kpi(self, product_id: uuid.UUID) -> Dict[str, any]:
        """
        상품 KPI 업데이트
        
        마켓별 노출/클릭 데이터와 주문 데이터를 집계하여 상품 KPI를 계산합니다.
        """
        product = self.db.get(Product, product_id)
        if not product:
            raise ValueError(f"Product not found: {product_id}")

        # 1. 노출/클릭 데이터 (Product 테이블의 기존 필드만 사용)
        total_views = product.total_views or 0
        total_clicks = product.total_clicks or 0

        # 2. 판매/수익 데이터 집계 (OrderItem, Order)
        sales_stmt = (
            select(
                func.sum(OrderItem.quantity).label("total_sales_count"),
                func.sum(OrderItem.quantity * OrderItem.unit_price).label("total_revenue"),
                func.count(func.distinct(Order.customer_id)).label("unique_customers")
            )
            .join(Order, OrderItem.order_id == Order.id)
            .where(OrderItem.product_id == product_id)
        )
        sales_result = self.db.execute(sales_stmt).one_or_none()

        total_sales_count = sales_result.total_sales_count or 0 if sales_result else 0
        total_revenue = int(sales_result.total_revenue or 0) if sales_result else 0
        unique_customers = sales_result.unique_customers or 0 if sales_result else 0

        # 3. CTR 계산
        ctr = total_clicks / total_views if total_views > 0 else 0.0

        # 4. 전환율 계산
        conversion_rate = total_sales_count / total_clicks if total_clicks > 0 else 0.0

        # 5. 고객당 평균 가치 계산
        avg_customer_value = total_revenue / unique_customers if unique_customers > 0 else 0.0

        # 6. 재구매 횟수 계산
        # (동일 고객이 2회 이상 구매한 경우)
        # 복잡한 쿼리가 필요하므로 여기서는 단순화
        # 추후 개선 필요
        repeat_purchase_count = self._calculate_repeat_purchases(product_id)

        # 7. 고객 유지율 계산 (재구매자 / 전체 고객)
        customer_retention_rate = (
            repeat_purchase_count / unique_customers
            if unique_customers > 0 else 0.0
        )

        # 상품 KPI 업데이트
        product.total_views = total_views
        product.total_clicks = total_clicks
        product.total_sales_count = total_sales_count
        product.total_revenue = total_revenue
        product.ctr = ctr
        product.conversion_rate = conversion_rate
        product.avg_customer_value = avg_customer_value
        product.repeat_purchase_count = repeat_purchase_count
        product.customer_retention_rate = customer_retention_rate

        self.db.commit()
        self.db.refresh(product)

        logger.info(f"Updated KPI for product {product_id}: "
                   f"views={total_views}, clicks={total_clicks}, "
                   f"sales={total_sales_count}, revenue={total_revenue}")

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

    def _get_kpi_snapshot(self, product: Product) -> Dict[str, any]:
        """현재 상품 KPI 스냅샷 생성"""
        return {
            "total_sales_count": product.total_sales_count,
            "total_views": product.total_views,
            "total_clicks": product.total_clicks,
            "ctr": product.ctr,
            "conversion_rate": product.conversion_rate,
            "repeat_purchase_count": product.repeat_purchase_count,
            "customer_retention_rate": product.customer_retention_rate,
            "total_revenue": product.total_revenue,
            "avg_customer_value": product.avg_customer_value,
            "lifecycle_stage": product.lifecycle_stage,
            "snapshot_at": datetime.now().isoformat()
        }

    def _get_days_listed(self, product: Product) -> int:
        """상품 등록 일수 계산 (단순화)"""
        # 현재 Product 모델의 기존 필드만 사용
        # 향후 노출/클릭 데이터가 업데이트되면 해당 필드 사용

        # 간접 연결: OrderItem ── Order → Product
        # 첫 주문일 기준으로 등록 일수 계산

        stmt = (
            select(func.min(Order.created_at))
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .where(OrderItem.product_id == product.id)
        )
        first_order_date = self.db.execute(stmt).scalar()

        if first_order_date:
            return (datetime.now() - first_order_date).days
        return 0

    def _get_days_in_stage(self, product: Product, stage: str) -> int:
        """특정 단계 체류 일수 계산"""
        if not product.lifecycle_stage_updated_at:
            return 0
        return (datetime.now() - product.lifecycle_stage_updated_at).days

    def _get_next_transition_sequence(self, product_id: uuid.UUID) -> int:
        """다음 전환 순서 번호 가져오기"""
        stmt = (
            select(func.max(ProductLifecycle.transition_sequence))
            .where(ProductLifecycle.product_id == product_id)
        )
        max_sequence = self.db.execute(stmt).scalar()
        return (max_sequence or 0) + 1

    def _calculate_repeat_purchases(self, product_id: uuid.UUID) -> int:
        """재구매 횟수 계산"""
        # 동일 고객이 2회 이상 구매한 횟수
        stmt = """
            SELECT COUNT(*) as repeat_count
            FROM (
                SELECT customer_id, COUNT(*) as order_count
                FROM orders o
                JOIN order_items oi ON o.id = oi.order_id
                WHERE oi.product_id = %s
                GROUP BY customer_id
                HAVING COUNT(*) >= 2
            ) repeat_customers
        """
        result = self.db.execute(stmt, [str(product_id)]).one_or_none()
        return result.repeat_count if result else 0

    def get_stage_distribution(self) -> Dict[str, int]:
        """
        단계별 상품 분포 통계
        
        Returns:
            {
                "STEP_1": 100,
                "STEP_2": 50,
                "STEP_3": 10
            }
        """
        stmt = (
            select(Product.lifecycle_stage, func.count(Product.id))
            .group_by(Product.lifecycle_stage)
        )
        results = self.db.execute(stmt).all()

        distribution = {
            "STEP_1": 0,
            "STEP_2": 0,
            "STEP_3": 0
        }

        for stage, count in results:
            distribution[stage] = count

        return distribution

    def get_transition_candidates(self, stage: str) -> List[Dict[str, any]]:
        """
        전환 가능한 상품 목록 조회
        
        Args:
            stage: "STEP_1" 또는 "STEP_2"
            
        Returns:
            전환 가능한 상품 정보 리스트
        """
        products = self.get_products_by_stage(stage, limit=1000)
        candidates = []

        for product in products:
            eligibility = self.check_transition_eligibility(product.id)
            if eligibility["eligible"]:
                candidates.append({
                    "product_id": str(product.id),
                    "name": product.name,
                    "current_stage": eligibility["current_stage"],
                    "next_stage": eligibility["next_stage"],
                    "kpi_snapshot": eligibility["kpi_snapshot"],
                    "criteria_met": eligibility["criteria_met"]
                })

        return candidates


