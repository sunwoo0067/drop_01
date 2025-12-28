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
    SourcingCandidate, BenchmarkProduct, SupplierItemRaw,
    MarketAccount, MarketListing
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
        
        # 옵션별 추천 계산
        option_recommendations = await self._calculate_option_recommendations(product_id)
        
        # 모델 생성
        recommendation = SourcingRecommendation(
            product_id=product_id,
            recommendation_type=recommendation_type,
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
            reasoning=prediction.get("reason") if recommendation_type == "REORDER" else None,
            option_recommendations=option_recommendations,
            status="PENDING"
        )
        
        self.db.add(recommendation)
        self.db.commit()
        return recommendation

    async def get_scaling_recommendations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        다채널 확장을 위한 상품 추천 목록을 생성합니다.
        (예: 쿠팡에서 잘 팔리는 상품을 스마트스토어에 확장)
        """
        # 1. 최근 14일간 판매 성과가 우수한 상품 조회 (주문 5건 이상)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=14)
        
        high_performers = (
            self.db.execute(
                select(Product.id, Product.name, func.count(Order.id).label("order_count"))
                .join(OrderItem, Product.id == OrderItem.product_id)
                .join(Order, OrderItem.order_id == Order.id)
                .where(Order.order_at >= cutoff_date)
                .group_by(Product.id, Product.name)
                .having(func.count(Order.id) >= 5)
                .order_by(func.count(Order.id).desc())
                .limit(50)
            )
            .all()
        )
        
        # 2. 사용 가능한 마켓 계정 확인
        market_accounts = self.db.execute(select(MarketAccount).where(MarketAccount.is_active == True)).scalars().all()
        available_markets = list(set([acc.market_code for acc in market_accounts]))
        
        recommendations = []
        for p_id, p_name, order_count in high_performers:
            # 해당 상품이 등록된 마켓들 확인 (MarketAccount와 조인하여 market_code 가져옴)
            listings = self.db.execute(
                select(MarketAccount.market_code)
                .join(MarketListing, MarketAccount.id == MarketListing.market_account_id)
                .where(MarketListing.product_id == p_id)
            ).scalars().all()
            
            listed_markets = list(set(listings))
            
            # 미등록 마켓 식별
            for market in available_markets:
                if market not in listed_markets:
                    # 확장 추천 생성
                    expected_impact = "High" if order_count > 15 else "Medium"
                    difficulty = "Low" # 기본적으로 이미 등록된 상품이므로 낮음
                    
                    recommendations.append({
                        "product_id": str(p_id),
                        "product_name": p_name,
                        "current_orders": order_count,
                        "source_market": listed_markets[0] if listed_markets else "UNKNOWN",
                        "target_market": market,
                        "expected_impact": expected_impact,
                        "difficulty_score": difficulty,
                        "potential_revenue": int(order_count * 20000 * 0.8), # 대략적인 추정
                        "reason": f"최근 14일간 {order_count}건의 주문이 발생한 검증된 상품입니다. {market} 채널 확장 시 추가 매출이 기대됩니다."
                    })
                    
        return recommendations[:limit]
        
        # AI 기반 추천 사유 생성
        reasoning = await self._generate_recommendation_reasoning(
            product, 
            analytics, 
            scores, 
            quantity_info,
            option_recommendations
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
            option_recommendations=option_recommendations,
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

    async def _calculate_option_recommendations(
        self,
        product_id: uuid.UUID
    ) -> List[Dict[str, Any]]:
        """
        옵션별 추천 상세 계산
        
        Args:
            product_id: 제품 ID
            
        Returns:
            옵션별 추천 목록
        """
        # 1. 옵션 성과 데이터 조회
        option_performance = await self.sales_analytics_service.get_option_performance(product_id)
        
        recommendations = []
        for opt in option_performance:
            # 점수 계산: 마진율(50%) + 판매량 점수(50%)
            margin_rate = opt.get("avg_margin_rate", 0.0)
            total_qty = opt.get("total_quantity", 0)
            
            margin_score = min(1.0, margin_rate * 5) * 50  # 20% 마진 = 50점
            volume_score = min(1.0, total_qty / 20) * 50  # 20개 판매 = 50점
            score = margin_score + volume_score
            
            # 추천 수량: 지난 판매량의 1.3배 보정 (시즌성 제외 기본 로직)
            # 판매량이 0인 경우 최소 5개 추천 (신규 진입 대비)
            rec_qty = int(total_qty * 1.3) if total_qty > 0 else 5
            
            oid = opt.get("option_id")
            if oid == "No Option":
                oid = None
                
            recommendations.append({
                "option_id": oid,
                "option_name": opt.get("option_name"),
                "option_value": opt.get("option_value"),
                "total_quantity": total_qty,
                "total_revenue": opt.get("total_revenue", 0),
                "total_profit": opt.get("total_profit", 0),
                "avg_margin_rate": margin_rate,
                "recommended_quantity": rec_qty,
                "score": score
            })
            
        # 점수 높은 순 정렬
        recommendations.sort(key=lambda x: x["score"], reverse=True)
        return recommendations
    
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
        """
        current_supply_price = product.cost_price
        recommended_selling_price = product.selling_price
        
        if recommended_selling_price == 0:
            recommended_selling_price = int(current_supply_price * 1.3)
        
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

    async def predict_optimal_price(self, product_id: uuid.UUID) -> Dict[str, Any]:
        """
        AI 모델을 사용하여 제품의 최적 판매가를 예측합니다.
        판매 속도(Velocity), 현재 이익률, 시장 수요를 종합 고려합니다.
        """
        product = self.db.get(Product, product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")

        # 최신 분석 데이터 가져오기
        analytics = (
            self.db.execute(
                select(SalesAnalytics)
                .where(SalesAnalytics.product_id == product_id)
                .order_by(SalesAnalytics.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

        if not analytics:
            analytics = await self.sales_analytics_service.analyze_product_sales(product_id)

        prompt = f"""
        당신은 이커머스 가격 전략 전문가입니다. 다음 데이터를 바탕으로 이 제품의 최적 판매가를 제안하세요.

        제품명: {product.name}
        매입 원가: {product.cost_price}원
        현재 판매가: {product.selling_price}원
        주간 주문수: {analytics.total_orders}건
        매출 성장률: {analytics.revenue_growth_rate:.1%}
        시장 수요 점수: {analytics.market_demand_score}/1.0

        가이드라인:
        - 판매 속도가 빠르고 성장세라면 이익률을 높이는 필승가 전략을 취하세요.
        - 재고가 많고 판매가 정체되었다면 공격적인 할인가 전략을 취하세요.
        - 마켓 수수료(약 12%)를 고려하여 역마진이 나지 않도록 하세요.

        반드시 다음 항목을 포함한 JSON 형식으로 응답하세요:
        1. "optimal_price": 제안하는 최적 판매가 (숫자)
        2. "strategy": 가격 전략 유형 (Premium, Competitive, Clearance 등)
        3. "reason": 가격 제안의 핵심 근거
        4. "expected_margin_rate": 제안 가격 적용 시 예상 이익률 (float 0-1)
        5. "impact": 가격 조정 시 예상되는 판매량 변화 (텍스트)
        """

        try:
            prediction = await self.ai_service.generate_json(prompt, provider="auto")
            
            # 마켓 리스팅 정보 추가 (실제 가격 수정을 위해 필요)
            listing = (
                self.db.execute(
                    select(MarketListing)
                    .where(MarketListing.product_id == product_id)
                    .order_by(MarketListing.linked_at.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            
            if listing:
                account = self.db.get(MarketAccount, listing.market_account_id)
                prediction["market_code"] = account.market_code if account else None
                prediction["account_id"] = str(listing.market_account_id)
                prediction["market_item_id"] = listing.market_item_id
            else:
                prediction["market_code"] = None
                prediction["account_id"] = None
                prediction["market_item_id"] = None

            return prediction
        except Exception as e:
            logger.error(f"Failed to predict optimal price for {product_id}: {e}")
            raise
    
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
    def _calculate_stock_info(
        self,
        product: Product
    ) -> Dict[str, Any]:
        """
        제품 재고 정보 분석 (실제 DB 데이터 연동)
        
        Args:
            product: 제품 객체
        
        Returns:
            재고 정보 딕셔너리
        """
        # 1. 실제 재고 조회 (하위 옵션들의 재고 합계)
        options = self.db.execute(
            select(ProductOption).where(ProductOption.product_id == product.id)
        ).scalars().all()
        
        current_stock = sum(opt.stock_quantity for opt in options)
        
        # 2. 재주문 시점 계산 (최근 14일간 평균 판매량의 7일치 재고분)
        # 기본값 10개, 또는 일평균 판매량 기준 유동적 설정
        reorder_point = 10 
        
        # 3. 재고 일수 계산
        stock_days_left = None
        
        # 최근 14일간 일평균 판매량 계산
        recent_orders = (
            self.db.execute(
                select(func.sum(OrderItem.quantity))
                .join(Order)
                .where(OrderItem.product_id == product.id)
                .where(Order.created_at >= datetime.now(timezone.utc) - timedelta(days=14))
            )
            .scalar()
        ) or 0
        
        daily_avg = recent_orders / 14.0
        
        if daily_avg > 0:
            stock_days_left = int(current_stock / daily_avg)
            # 재주문 포인트 자동 보정: 7일치 일평균 판매량
            reorder_point = max(10, int(daily_avg * 7))
        elif current_stock > 0:
            # 판매가 없는데 재고는 있는 경우 99일 이상으로 표시
            stock_days_left = 99
        else:
            stock_days_left = 0
            
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
        quantity_info: Dict[str, int],
        option_recommendations: List[Dict[str, Any]] = None
    ) -> str:
        """
        추천 사유 생성 (옵션 인사이트 포함)
        """
        try:
            # 상위 3개 옵션 성과 요약
            option_context = ""
            if option_recommendations:
                top_opts = option_recommendations[:3]
                option_context = "Top Performing Options:\n" + "\n".join([
                    f"- {o['option_name']}({o['option_value']}): {o['total_quantity']} sold, {o['avg_margin_rate']:.1%} margin"
                    for o in top_opts
                ])

            prompt = f"""
            Generate a strategic sourcing recommendation summary for this product:
            
            Product: {product.name}
            Stats: {analytics.total_orders} orders, {analytics.avg_margin_rate:.1%} avg margin.
            
            {option_context}
            
            Recommendation:
            - Total Recommended Qty: {quantity_info['recommended_quantity']} units
            - Overall Score: {scores['overall_score']:.1f}/100
            
            Focus on which options are driving profits and if any specific variations should be prioritized or avoided.
            Return ONLY a single paragraph in Korean (max 300 characters).
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
        대량 소싱 추천 생성 (판매 상위 및 위험군 우선)
        """
        # 1. 최근 30일간 판매량이 있는 제품 우선 선별
        # 2. 또는 재고 임계치 이하인 활성 제품
        
        # 최근 판매 제품 ID 추출
        recent_selling_ids = (
            self.db.execute(
                select(OrderItem.product_id)
                .join(Order)
                .where(Order.created_at >= datetime.now(timezone.utc) - timedelta(days=30))
                .group_by(OrderItem.product_id)
                .order_by(func.sum(OrderItem.quantity).desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        
        query = select(Product).where(Product.status == "ACTIVE")
        if recent_selling_ids:
            # 판매 이력이 있는 제품을 우선으로 하되, 부족하면 다른 활성 상품 포함
            query = query.where(
                or_(
                    Product.id.in_(recent_selling_ids),
                    # 재고가 적은 상품도 포함 로직 (추후 확장 가능)
                    # 현재는 판매 이력 있는 상품만 우선, limit에 도달하지 못하면 다른 활성 상품으로 채움
                    # TODO: 재고 임계치 이하 상품 포함 로직 추가
                )
            ).order_by(func.random()) # 매번 다양한 상품이 섞이도록 랜덤성 추가 (또는 판매순)
        
        products = self.db.execute(query.limit(limit)).scalars().all()
        
        recommendations = []
        for product in products:
            try:
                # 개별 추천 생성 (이미 오늘 생성된 경우 기존 것 반환)
                rec = await self.generate_product_recommendation(
                    product.id, 
                    recommendation_type=recommendation_type
                )
                recommendations.append(rec)
            except Exception as e:
                logger.error(f"Failed to generate bulk recommendation for {product.id}: {e}")
                
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
