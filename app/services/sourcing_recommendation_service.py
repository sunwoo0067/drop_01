"""
Sourcing Recommendation Service

AI 기반 소싱 추천 및 자동 재주문 예측을 담당하는 서비스입니다.
판매 데이터, 시장 트렌드, 재고 상태를 종합적으로 분석하여 소싱 추천을 제공합니다.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from app.models import (
    SalesAnalytics, Order, OrderItem, Product, 
    SourcingRecommendation, SupplierPerformance,
    SourcingCandidate, BenchmarkProduct, SupplierItemRaw
)
from app.services.sales_analytics_service import SalesAnalyticsService
from app.services.ai import AIService
from app.services.ai.exceptions import wrap_exception, AIError

logger = logging.getLogger(__name__)


class SourcingRecommendationService:
    """
    AI 기반 소싱 추천 서비스
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.ai_service = AIService()
        self.sales_analytics_service = SalesAnalyticsService(db)
    
    async def generate_product_recommendation(
        self,
        product_id: uuid.UUID,
        recommendation_type: str = "REORDER"
    ) -> SourcingRecommendation:
        """
        제품별 소싱 추천 생성
        
        Args:
            product_id: 제품 ID
            recommendation_type: 추천 유형 ('NEW_PRODUCT', 'REORDER', 'ALTERNATIVE')
        
        Returns:
            SourcingRecommendation 인스턴스
        """
        product = self.db.get(Product, product_id)
        if not product:
            raise ValueError(f"Product not found: {product_id}")
        
        # 기존 추천 확인 (오늘 날짜 기준)
        today = datetime.now(timezone.utc).date()
        existing = (
            self.db.execute(
                select(SourcingRecommendation)
                .where(SourcingRecommendation.product_id == product_id)
                .where(func.date(SourcingRecommendation.recommendation_date) == today)
                .where(SourcingRecommendation.recommendation_type == recommendation_type)
            )
            .scalars()
            .first()
        )
        
        if existing:
            logger.info(f"Using existing recommendation for product {product_id}")
            return existing
        
        # 판매 데이터 분석
        analytics = await self.sales_analytics_service.analyze_product_sales(product_id)
        
        # 점수 계산
        scores = await self._calculate_recommendation_scores(
            product, 
            analytics, 
            recommendation_type
        )
        
        # 추천 수량 계산
        quantity_info = self._calculate_recommended_quantity(
            product, 
            analytics, 
            scores
        )
        
        # 가격 정보
        price_info = self._calculate_price_info(product, analytics)
        
        # 재고 정보
        stock_info = self._calculate_stock_info(product)
        
        # 공급처 신뢰도 점수
        supplier_score = await self._calculate_supplier_score(product)
        
        # AI 기반 추천 사유 생성
        reasoning = await self._generate_recommendation_reasoning(
            product, 
            analytics, 
            scores, 
            quantity_info
        )
        
        # 리스크 및 기회 요소
        risk_factors = await self._analyze_risk_factors(product, analytics)
        opportunity_factors = await self._analyze_opportunity_factors(product, analytics)
        
        # 추천 생성
        recommendation = SourcingRecommendation(
            product_id=product_id,
            supplier_item_id=product.supplier_item_id,
            recommendation_type=recommendation_type,
            recommendation_date=datetime.now(timezone.utc),
            overall_score=scores["overall_score"],
            sales_potential_score=scores["sales_potential_score"],
            market_trend_score=scores["market_trend_score"],
            profit_margin_score=scores["profit_margin_score"],
            supplier_reliability_score=supplier_score,
            seasonal_score=scores["seasonal_score"],
            recommended_quantity=quantity_info["recommended_quantity"],
            min_quantity=quantity_info["min_quantity"],
            max_quantity=quantity_info["max_quantity"],
            current_supply_price=price_info["current_supply_price"],
            recommended_selling_price=price_info["recommended_selling_price"],
            expected_margin=price_info["expected_margin"],
            current_stock=stock_info["current_stock"],
            stock_days_left=stock_info["stock_days_left"],
            reorder_point=stock_info["reorder_point"],
            reasoning=reasoning,
            risk_factors=risk_factors,
            opportunity_factors=opportunity_factors,
            status="PENDING",
            confidence_level=scores.get("confidence_level", 0.5)
        )
        
        self.db.add(recommendation)
        self.db.commit()
        
        logger.info(
            f"Created sourcing recommendation for product {product_id}: "
            f"score={scores['overall_score']:.2f}, quantity={quantity_info['recommended_quantity']}"
        )
        
        return recommendation
    
    async def _calculate_recommendation_scores(
        self,
        product: Product,
        analytics: SalesAnalytics,
        recommendation_type: str
    ) -> Dict[str, float]:
        """
        추천 점수 계산
        
        Args:
            product: 제품 객체
            analytics: 판매 분석 데이터
            recommendation_type: 추천 유형
        
        Returns:
            점수 딕셔너리
        """
        # 1. 판매 잠재력 점수 (30%)
        sales_potential_score = 0.0
        if analytics.total_orders > 0:
            # 주문 성장률과 예측 수량 기반
            growth_factor = max(0, analytics.order_growth_rate)
            prediction_factor = min(1.0, (analytics.predicted_orders or 0) / max(1, analytics.total_orders))
            sales_potential_score = (growth_factor * 0.5 + prediction_factor * 0.5) * 100
        
        # 2. 시장 트렌드 점수 (25%)
        market_trend_score = (
            analytics.category_trend_score * 50 + 
            analytics.market_demand_score * 50
        )
        
        # 3. 이익률 점수 (25%)
        profit_margin_score = min(100, analytics.avg_margin_rate * 500)  # 20% 마진 = 100점
        
        # 4. 시즌성 점수 (20%)
        seasonal_score = 50.0  # 기본값
        if product.benchmark_product_id:
            benchmark = self.db.get(BenchmarkProduct, product.benchmark_product_id)
            if benchmark:
                # 시즌성 분석 (간단 구현)
                current_month = datetime.now().month
                # 여름 시즌 제품 (6-8월)
                if current_month in [6, 7, 8]:
                    seasonal_score = 70.0
                # 연말 시즌 제품 (11-12월)
                elif current_month in [11, 12]:
                    seasonal_score = 90.0
                # 봄 시즌 제품 (3-5월)
                elif current_month in [3, 4, 5]:
                    seasonal_score = 80.0
        
        # 종합 점수 (가중평균)
        overall_score = (
            sales_potential_score * 0.30 +
            market_trend_score * 0.25 +
            profit_margin_score * 0.25 +
            seasonal_score * 0.20
        )
        
        # 추천 유형별 보정
        if recommendation_type == "NEW_PRODUCT":
            # 신규 제품은 시장 트렌드 가중치 증가
            overall_score = (
                sales_potential_score * 0.20 +
                market_trend_score * 0.40 +
                profit_margin_score * 0.30 +
                seasonal_score * 0.10
            )
        elif recommendation_type == "REORDER":
            # 재주문은 판매 잠재력 가중치 증가
            overall_score = (
                sales_potential_score * 0.40 +
                market_trend_score * 0.20 +
                profit_margin_score * 0.30 +
                seasonal_score * 0.10
            )
        
        return {
            "overall_score": overall_score,
            "sales_potential_score": sales_potential_score,
            "market_trend_score": market_trend_score,
            "profit_margin_score": profit_margin_score,
            "seasonal_score": seasonal_score,
            "confidence_level": analytics.prediction_confidence or 0.5
        }
    
    def _calculate_recommended_quantity(
        self,
        product: Product,
        analytics: SalesAnalytics,
        scores: Dict[str, float]
    ) -> Dict[str, int]:
        """
        추천 수량 계산
        
        Args:
            product: 제품 객체
            analytics: 판매 분석 데이터
            scores: 점수 데이터
        
        Returns:
            수량 정보 딕셔너리
        """
        # 기본 수량: 최근 주문량 기반
        base_quantity = max(1, analytics.total_quantity)
        
        # 예측 수량
        predicted_quantity = base_quantity
        if analytics.predicted_orders:
            # 평균 주문당 수량 가정
            avg_qty_per_order = base_quantity / max(1, analytics.total_orders)
            predicted_quantity = int(analytics.predicted_orders * avg_qty_per_order)
        
        # 점수 기반 조정
        score_factor = scores["overall_score"] / 100.0
        recommended_quantity = int(predicted_quantity * (0.5 + score_factor))
        
        # 최소/최대 수량 설정
        min_quantity = max(1, int(predicted_quantity * 0.5))
        max_quantity = int(predicted_quantity * 2.0)
        
        # 시즌성 보정
        if scores["seasonal_score"] > 70:
            recommended_quantity = int(recommended_quantity * 1.3)
        
        return {
            "recommended_quantity": recommended_quantity,
            "min_quantity": min_quantity,
            "max_quantity": max_quantity
        }
    
    def _calculate_price_info(
        self,
        product: Product,
        analytics: SalesAnalytics
    ) -> Dict[str, Any]:
        """
        가격 정보 계산
        
        Args:
            product: 제품 객체
            analytics: 판매 분석 데이터
        
        Returns:
            가격 정보 딕셔너리
        """
        current_supply_price = product.cost_price
        
        # 추천 판매가: 현재 판매가 또는 마진률 기반 계산
        recommended_selling_price = product.selling_price
        if recommended_selling_price == 0:
            # 기본 30% 마진
            recommended_selling_price = int(current_supply_price * 1.3)
        
        # 예상 마진률
        expected_margin = (
            (recommended_selling_price - current_supply_price) 
            / recommended_selling_price 
            if recommended_selling_price > 0 else 0
        )
        
        return {
            "current_supply_price": current_supply_price,
            "recommended_selling_price": recommended_selling_price,
            "expected_margin": expected_margin
        }
    
    def _calculate_stock_info(
        self,
        product: Product
    ) -> Dict[str, Any]:
        """
        재고 정보 계산
        
        Args:
            product: 제품 객체
        
        Returns:
            재고 정보 딕셔너리
        """
        # 현재 재고 (간단 구현 - 실제로는 재고 테이블에서 조회 필요)
        current_stock = 0  # TODO: 실제 재고 데이터 연동
        
        # 재주문 시점: 최근 2주간 주문량
        # 간단 구현 - 실제로는 주문 데이터 기반 계산
        reorder_point = 10  # 기본값
        
        # 재고 일수 계산
        stock_days_left = None
        if current_stock > 0:
            # 최근 일일 평균 판매량
            recent_orders = (
                self.db.execute(
                    select(func.sum(OrderItem.quantity))
                    .join(Order)
                    .where(OrderItem.product_id == product.id)
                    .where(Order.created_at >= datetime.now(timezone.utc) - timedelta(days=7))
                )
                .scalar()
            ) or 0
            
            daily_avg = recent_orders / 7.0
            if daily_avg > 0:
                stock_days_left = int(current_stock / daily_avg)
        
        return {
            "current_stock": current_stock,
            "stock_days_left": stock_days_left,
            "reorder_point": reorder_point
        }
    
    async def _calculate_supplier_score(
        self,
        product: Product
    ) -> float:
        """
        공급처 신뢰도 점수 계산
        
        Args:
            product: 제품 객체
        
        Returns:
            공급처 신뢰도 점수 (0-100)
        """
        # 공급처 코드 확인
        supplier_code = None
        if product.supplier_item_id:
            raw_item = self.db.get(SupplierItemRaw, product.supplier_item_id)
            if raw_item:
                supplier_code = raw_item.supplier_code
        
        if not supplier_code:
            return 50.0  # 기본값
        
        # 최근 공급처 성능 조회
        performance = (
            self.db.execute(
                select(SupplierPerformance)
                .where(SupplierPerformance.supplier_code == supplier_code)
                .order_by(SupplierPerformance.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        
        if performance:
            return performance.overall_reliability_score
        
        return 50.0  # 기본값
    
    async def _generate_recommendation_reasoning(
        self,
        product: Product,
        analytics: SalesAnalytics,
        scores: Dict[str, float],
        quantity_info: Dict[str, int]
    ) -> str:
        """
        추천 사유 생성
        
        Args:
            product: 제품 객체
            analytics: 판매 분석 데이터
            scores: 점수 데이터
            quantity_info: 수량 정보
        
        Returns:
            추천 사유 문자열
        """
        try:
            prompt = f"""
            Generate a concise recommendation reasoning for sourcing this product:
            
            Product: {product.name}
            Current Price: {product.cost_price} -> {product.selling_price}
            
            Sales Performance:
            - Total Orders: {analytics.total_orders}
            - Revenue: {analytics.total_revenue}
            - Margin Rate: {analytics.avg_margin_rate:.2%}
            - Growth Rate: {analytics.order_growth_rate:.2%}
            
            Scores:
            - Sales Potential: {scores['sales_potential_score']:.1f}/100
            - Market Trend: {scores['market_trend_score']:.1f}/100
            - Profit Margin: {scores['profit_margin_score']:.1f}/100
            - Seasonal: {scores['seasonal_score']:.1f}/100
            
            Recommendation:
            - Quantity: {quantity_info['recommended_quantity']} units
            - Overall Score: {scores['overall_score']:.1f}/100
            
            Return ONLY a single paragraph explanation (max 200 words).
            """
            
            reasoning = await self.ai_service.generate_text(prompt, provider="auto")
            return reasoning[:500]  # 길이 제한
            
        except Exception as e:
            logger.warning(f"Reasoning generation failed: {e}")
            return (
                f"Based on sales analysis, this product shows "
                f"{analytics.order_growth_rate:.0%} order growth "
                f"with {analytics.avg_margin_rate:.0%} margin rate. "
                f"Recommended quantity: {quantity_info['recommended_quantity']}."
            )
    
    async def _analyze_risk_factors(
        self,
        product: Product,
        analytics: SalesAnalytics
    ) -> List[str]:
        """
        리스크 요소 분석
        
        Args:
            product: 제품 객체
            analytics: 판매 분석 데이터
        
        Returns:
            리스크 요소 목록
        """
        risks = []
        
        # 성장률 감소
        if analytics.order_growth_rate < -0.1:
            risks.append("Declining order trend (-10% or worse)")
        
        # 낮은 이익률
        if analytics.avg_margin_rate < 0.15:
            risks.append("Low profit margin (<15%)")
        
        # 낮은 시장 수요
        if analytics.market_demand_score < 0.3:
            risks.append("Low market demand score")
        
        # 예측 신뢰도 낮음
        if analytics.prediction_confidence and analytics.prediction_confidence < 0.5:
            risks.append("Low prediction confidence")
        
        return risks
    
    async def _analyze_opportunity_factors(
        self,
        product: Product,
        analytics: SalesAnalytics
    ) -> List[str]:
        """
        기회 요소 분석
        
        Args:
            product: 제품 객체
            analytics: 판매 분석 데이터
        
        Returns:
            기회 요소 목록
        """
        opportunities = []
        
        # 높은 성장률
        if analytics.order_growth_rate > 0.2:
            opportunities.append(f"Strong growth trend (+{analytics.order_growth_rate:.0%})")
        
        # 높은 이익률
        if analytics.avg_margin_rate > 0.25:
            opportunities.append(f"High profit margin ({analytics.avg_margin_rate:.0%})")
        
        # 높은 시장 수요
        if analytics.market_demand_score > 0.7:
            opportunities.append("High market demand")
        
        # 긍정적인 예측
        if analytics.predicted_orders and analytics.predicted_orders > analytics.total_orders:
            growth_pct = (
                (analytics.predicted_orders - analytics.total_orders) 
                / max(1, analytics.total_orders)
            )
            opportunities.append(f"Predicted growth (+{growth_pct:.0%})")
        
        return opportunities
    
    async def generate_bulk_recommendations(
        self,
        limit: int = 50,
        recommendation_type: str = "REORDER"
    ) -> List[SourcingRecommendation]:
        """
        대량 소싱 추천 생성
        
        Args:
            limit: 생성할 추천 수
            recommendation_type: 추천 유형
        
        Returns:
            생성된 추천 목록
        """
        # 활성 제품 조회
        products = (
            self.db.execute(
                select(Product)
                .where(Product.status == "ACTIVE")
                .limit(limit)
            )
            .scalars()
            .all()
        )
        
        recommendations = []
        for product in products:
            try:
                recommendation = await self.generate_product_recommendation(
                    product.id, 
                    recommendation_type
                )
                recommendations.append(recommendation)
            except Exception as e:
                logger.error(f"Failed to generate recommendation for product {product.id}: {e}")
        
        logger.info(f"Generated {len(recommendations)} sourcing recommendations")
        return recommendations
    
    def get_pending_recommendations(
        self,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        대기 중인 추천 조회
        
        Args:
            limit: 조회할 추천 수
        
        Returns:
            대기 중인 추천 목록
        """
        recommendations = (
            self.db.execute(
                select(SourcingRecommendation)
                .where(SourcingRecommendation.status == "PENDING")
                .order_by(SourcingRecommendation.overall_score.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        
        results = []
        for rec in recommendations:
            product = self.db.get(Product, rec.product_id) if rec.product_id else None
            results.append({
                "id": str(rec.id),
                "product_id": str(rec.product_id) if rec.product_id else None,
                "product_name": product.name if product else "Unknown",
                "recommendation_type": rec.recommendation_type,
                "overall_score": rec.overall_score,
                "recommended_quantity": rec.recommended_quantity,
                "current_supply_price": rec.current_supply_price,
                "recommended_selling_price": rec.recommended_selling_price,
                "expected_margin": rec.expected_margin,
                "reasoning": rec.reasoning,
                "risk_factors": rec.risk_factors,
                "opportunity_factors": rec.opportunity_factors,
                "created_at": rec.created_at.isoformat() if rec.created_at else None
            })
        
        return results
    
    def accept_recommendation(
        self,
        recommendation_id: uuid.UUID,
        action_taken: str = "ORDER_PLACED",
        auto_create_product: bool = True
    ) -> SourcingRecommendation:
        """
        추천 수락
        
        Args:
            recommendation_id: 추천 ID
            action_taken: 수행된 액션
            auto_create_product: 자동으로 상품 생성 여부
        
        Returns:
            업데이트된 추천
        """
        recommendation = self.db.get(SourcingRecommendation, recommendation_id)
        if not recommendation:
            raise ValueError(f"Recommendation not found: {recommendation_id}")
        
        recommendation.status = "ACCEPTED"
        recommendation.action_taken = action_taken
        self.db.commit()
        
        logger.info(f"Recommendation {recommendation_id} accepted: {action_taken}")
        
        # 자동 상품 생성
        if auto_create_product and recommendation.product_id:
            try:
                self._auto_create_product_from_recommendation(recommendation)
            except Exception as e:
                logger.error(f"Failed to auto-create product from recommendation {recommendation_id}: {e}")
        
        return recommendation
    
    def _auto_create_product_from_recommendation(
        self,
        recommendation: SourcingRecommendation
    ):
        """
        추천에서 자동으로 상품 생성
        
        Args:
            recommendation: 소싱 추천 객체
        """
        from app.normalization import clean_product_name
        from app.services.ai import AIService
        
        # 이미 Product가 생성되었는지 확인
        if not recommendation.product_id:
            logger.warning(f"Recommendation {recommendation.id} has no product_id, skipping auto-create")
            return
        
        existing_product = (
            self.db.execute(
                select(Product).where(Product.id == recommendation.product_id)
            )
            .scalars()
            .first()
        )
        
        if existing_product:
            logger.info(f"Product already exists for recommendation {recommendation.id}: {existing_product.id}")
            return
        
        # SupplierItemRaw 조회
        raw_entry = None
        if recommendation.supplier_item_id:
            raw_entry = self.db.get(SupplierItemRaw, recommendation.supplier_item_id)
        
        if not raw_entry:
            logger.warning(f"SupplierItemRaw not found for recommendation {recommendation.id}, skipping auto-create")
            return
        
        # Product 생성
        ai = AIService()
        
        # 원본 이름 정제
        cleaned_name = clean_product_name(raw_entry.raw.get("item_name") or raw_entry.raw.get("name") or "Unknown Product")
        
        # SEO 최적화
        seo = ai.optimize_seo(
            cleaned_name,
            [],
            context=recommendation.reasoning
        )
        processed_name = seo.get("title") or cleaned_name
        processed_keywords = seo.get("tags") or []
        
        # 가격 설정
        cost_price = recommendation.current_supply_price
        selling_price = recommendation.recommended_selling_price
        
        product = Product(
            supplier_item_id=raw_entry.id,
            name=cleaned_name,
            processed_name=processed_name,
            processed_keywords=processed_keywords,
            cost_price=cost_price,
            selling_price=selling_price,
            status="DRAFT",
            processing_status="PENDING",
            processed_image_urls=[],
            benchmark_product_id=None  # 추천 기반이므로 벤치마크 없음
        )
        
        self.db.add(product)
        self.db.flush()
        
        logger.info(
            f"Auto-created product from recommendation {recommendation.id}: "
            f"{product.name} (ID: {product.id}), "
            f"cost={cost_price}, selling={selling_price}"
        )
        
        # 추천 상태 업데이트 (COMPLETED로 변경)
        recommendation.status = "COMPLETED"
        self.db.commit()
        
        return product
    
    def reject_recommendation(
        self,
        recommendation_id: uuid.UUID,
        action_taken: str = "REJECTED"
    ) -> SourcingRecommendation:
        """
        추천 거부
        
        Args:
            recommendation_id: 추천 ID
            action_taken: 수행된 액션
        
        Returns:
            업데이트된 추천
        """
        recommendation = self.db.get(SourcingRecommendation, recommendation_id)
        if not recommendation:
            raise ValueError(f"Recommendation not found: {recommendation_id}")
        
        recommendation.status = "REJECTED"
        recommendation.action_taken = action_taken
        self.db.commit()
        
        logger.info(f"Recommendation {recommendation_id} rejected: {action_taken}")
        return recommendation
    
    def get_recommendation_summary(
        self,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        추천 요약 통계
        
        Args:
            days: 조회할 일수
        
        Returns:
            요약 통계
        """
        since_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # 전체 추천
        total = (
            self.db.execute(
                select(func.count(SourcingRecommendation.id))
                .where(SourcingRecommendation.created_at >= since_date)
            )
            .scalar()
        ) or 0
        
        # 상태별 카운트
        pending = (
            self.db.execute(
                select(func.count(SourcingRecommendation.id))
                .where(SourcingRecommendation.created_at >= since_date)
                .where(SourcingRecommendation.status == "PENDING")
            )
            .scalar()
        ) or 0
        
        accepted = (
            self.db.execute(
                select(func.count(SourcingRecommendation.id))
                .where(SourcingRecommendation.created_at >= since_date)
                .where(SourcingRecommendation.status == "ACCEPTED")
            )
            .scalar()
        ) or 0
        
        rejected = (
            self.db.execute(
                select(func.count(SourcingRecommendation.id))
                .where(SourcingRecommendation.created_at >= since_date)
                .where(SourcingRecommendation.status == "REJECTED")
            )
            .scalar()
        ) or 0
        
        # 평균 점수
        avg_score = (
            self.db.execute(
                select(func.avg(SourcingRecommendation.overall_score))
                .where(SourcingRecommendation.created_at >= since_date)
            )
            .scalar()
        ) or 0.0
        
        return {
            "period_days": days,
            "total_recommendations": total,
            "pending": pending,
            "accepted": accepted,
            "rejected": rejected,
            "acceptance_rate": (accepted / total * 100) if total > 0 else 0,
            "avg_overall_score": float(avg_score)
        }


def create_sourcing_recommendation_service(db: Session) -> SourcingRecommendationService:
    """
    SourcingRecommendationService 인스턴스 생성 헬퍼
    
    Args:
        db: 데이터베이스 세션
    
    Returns:
        SourcingRecommendationService 인스턴스
    """
    return SourcingRecommendationService(db)
