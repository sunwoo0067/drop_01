"""
Sales Analytics Service

판매 데이터 분석 및 AI 기반 예측을 담당하는 서비스입니다.
소싱 추천을 위한 판매 데이터 기반 분석을 제공합니다.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from app.models import (
    SalesAnalytics, Order, OrderItem, Product, ProductOption,
    SourcingRecommendation, SupplierPerformance,
    SourcingCandidate, BenchmarkProduct,
    MarketRevenueRaw, MarketSettlementRaw,
    MarketAccount, MarketFeePolicy, MarketListing
)
from app.services.ai import AIService
from app.services.ai.exceptions import wrap_exception, AIError

logger = logging.getLogger(__name__)


class SalesAnalyticsService:
    """
    판매 데이터 분석 및 예측 서비스
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.ai_service = AIService()
    
    async def analyze_product_sales(
        self,
        product_id: uuid.UUID,
        period_type: str = "weekly",
        period_count: int = 4
    ) -> SalesAnalytics:
        """
        제품별 판매 데이터를 분석합니다.
        
        Args:
            product_id: 제품 ID
            period_type: 분석 기간 유형 ('daily', 'weekly', 'monthly')
            period_count: 분석할 기간 수
        
        Returns:
            SalesAnalytics 인스턴스
        """
        product = self.db.get(Product, product_id)
        if not product:
            raise ValueError(f"Product not found: {product_id}")
        
        # 기간 계산
        period_end = datetime.now(timezone.utc)
        period_start = self._calculate_period_start(period_end, period_type, period_count)
        
        # 기존 분석 결과 확인
        existing = (
            self.db.execute(
                select(SalesAnalytics)
                .where(SalesAnalytics.product_id == product_id)
                .where(SalesAnalytics.period_type == period_type)
                .where(SalesAnalytics.period_start == period_start)
            )
            .scalars()
            .first()
        )
        
        if existing:
            logger.info(f"Using existing analytics for product {product_id}")
            return existing
        
        # 주문 데이터 수집
        order_stats = self._collect_order_stats(product_id, period_start, period_end)
        
        # 실제 마켓 데이터 수집 (쿠팡 등 정산 데이터 반영)
        actual_stats = self._collect_actual_market_stats(product_id, period_start, period_end)
        if actual_stats["actual_revenue"] > 0:
            logger.info(f"Using actual market revenue for product {product_id}")
            order_stats["total_revenue"] = actual_stats["actual_revenue"]
            order_stats["total_profit"] = actual_stats["actual_profit"]
            order_stats["avg_margin_rate"] = (actual_stats["actual_profit"] / actual_stats["actual_revenue"]) if actual_stats["actual_revenue"] > 0 else 0.0
        
        # 전 대비 성장률 계산
        growth_stats = self._calculate_growth_rate(
            product_id, 
            period_type, 
            period_start, 
            order_stats
        )
        
        # AI 기반 예측
        prediction_stats = await self._predict_future_sales(
            product, 
            order_stats, 
            period_type
        )
        
        # 카테고리/시장 트렌드 점수
        trend_scores = await self._calculate_trend_scores(product)
        
        # AI 기반 인사이트 생성
        insights = await self._generate_insights(product, order_stats, growth_stats)
        
        # 분석 결과 생성
        analytics = SalesAnalytics(
            product_id=product_id,
            period_type=period_type,
            period_start=period_start,
            period_end=period_end,
            total_orders=order_stats["total_orders"],
            total_quantity=order_stats["total_quantity"],
            total_revenue=order_stats["total_revenue"],
            total_profit=order_stats["total_profit"],
            avg_margin_rate=order_stats["avg_margin_rate"],
            order_growth_rate=growth_stats["order_growth_rate"],
            revenue_growth_rate=growth_stats["revenue_growth_rate"],
            predicted_orders=prediction_stats.get("predicted_orders"),
            predicted_revenue=prediction_stats.get("predicted_revenue"),
            prediction_confidence=prediction_stats.get("confidence"),
            category_trend_score=trend_scores["category_trend_score"],
            market_demand_score=trend_scores["market_demand_score"],
            trend_analysis=insights.get("trend_analysis"),
            insights=insights.get("insights", []),
            recommendations=insights.get("recommendations", []),
        )
        
        self.db.add(analytics)
        self.db.commit()
        
        logger.info(
            f"Created sales analytics for product {product_id}: "
            f"{order_stats['total_orders']} orders, {order_stats['total_revenue']} revenue"
        )
        
        return analytics
    
    def _calculate_period_start(
        self, 
        period_end: datetime, 
        period_type: str, 
        period_count: int
    ) -> datetime:
        """분석 시작일 계산"""
        if period_type == "daily":
            return period_end - timedelta(days=period_count)
        elif period_type == "weekly":
            return period_end - timedelta(weeks=period_count)
        elif period_type == "monthly":
            # 대략적인 월 계산 (30일 기준)
            return period_end - timedelta(days=period_count * 30)
        else:
            return period_end - timedelta(days=period_count * 7)
    
    def _collect_order_stats(
        self, 
        product_id: uuid.UUID, 
        period_start: datetime, 
        period_end: datetime
    ) -> Dict[str, Any]:
        """주문 통계 수집"""
        # 주문 아이템 조회
        order_items = (
            self.db.execute(
                select(OrderItem)
                .join(Order)
                .where(OrderItem.product_id == product_id)
                .where(Order.created_at >= period_start)
                .where(Order.created_at <= period_end)
            )
            .scalars()
            .all()
        )
        
        # 옵션 정보 수동 조회 (교차 DB 관계 미지원 대응)
        option_ids = [oi.product_option_id for oi in order_items if oi.product_option_id]
        options_map = {}
        if option_ids:
            options = self.db.execute(
                select(ProductOption).where(ProductOption.id.in_(option_ids))
            ).scalars().all()
            options_map = {opt.id: opt for opt in options}
        
        total_orders = len(set(oi.order_id for oi in order_items))
        total_quantity = sum(oi.quantity for oi in order_items)
        total_revenue = sum(oi.total_price for oi in order_items)
        
        # 이익률 계산 (메모리 내 옵션 맵 활용)
        product = self.db.get(Product, product_id)
        if product:
            total_cost = 0
            for oi in order_items:
                opt = options_map.get(oi.product_option_id)
                cost_per_unit = opt.cost_price if opt else product.cost_price
                total_cost += cost_per_unit * oi.quantity
            
            total_profit = total_revenue - total_cost
            avg_margin_rate = (total_profit / total_revenue) if total_revenue > 0 else 0.0
        else:
            total_profit = 0
            avg_margin_rate = 0.0
        
        return {
            "total_orders": total_orders,
            "total_quantity": total_quantity,
            "total_revenue": total_revenue,
            "total_profit": total_profit,
            "avg_margin_rate": avg_margin_rate
        }

    def _get_market_fee_rate(self, market_code: str, category_id: str | None = None) -> float:
        """
        MarketFeePolicy 테이블에서 수수료율을 조회합니다.
        """
        # 1. 특정 카테고리 수수료 조회
        if category_id:
            policy = self.db.execute(
                select(MarketFeePolicy)
                .where(MarketFeePolicy.market_code == market_code)
                .where(MarketFeePolicy.category_id == category_id)
            ).scalars().first()
            if policy:
                return policy.fee_rate
        
        # 2. 마켓 기본 수수료 조회 (category_id IS NULL)
        policy = self.db.execute(
            select(MarketFeePolicy)
            .where(MarketFeePolicy.market_code == market_code)
            .where(MarketFeePolicy.category_id == None)
        ).scalars().first()
        if policy:
            return policy.fee_rate
            
        # 3. 기본값 (정책 데이터가 없는 경우)
        return 0.108 if market_code == "COUPANG" else 0.06

    def _collect_actual_market_stats(
        self,
        product_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime
    ) -> Dict[str, Any]:
        """
        MarketRevenueRaw 데이터를 기반으로 실제 매출 및 비용(수수료 등)을 집계합니다.
        데이터가 없는 경우 마켓별 예상 수수료를 적용하여 추정합니다.
        """
        # 해당 상품의 마켓 정보 조회
        market_code = "COUPANG" # 기본값
        product = self.db.get(Product, product_id)
        
        # 1. 실제 정산/매출 데이터 조회 시도
        order_numbers = (
            self.db.execute(
                select(Order.order_number)
                .join(OrderItem, Order.id == OrderItem.order_id)
                .where(OrderItem.product_id == product_id)
                .where(Order.created_at >= period_start)
                .where(Order.created_at <= period_end)
            )
            .scalars()
            .all()
        )
        
        revenue_items = []
        if order_numbers:
            revenue_items = (
                self.db.execute(
                    select(MarketRevenueRaw)
                    .where(MarketRevenueRaw.order_id.in_(order_numbers))
                )
                .scalars()
                .all()
            )
        
        total_actual_revenue = 0
        total_fees = 0
        
        if revenue_items:
            for item in revenue_items:
                raw = item.raw
                sale_amount = raw.get("saleAmount", 0)
                settlement_amount = raw.get("settlementTargetAmount", 0)
                total_actual_revenue += sale_amount
                total_fees += (sale_amount - settlement_amount)
        else:
            # 실 데이터가 없으면 주문 테이블 기반으로 추정
            # 해당 상품이 등록된 마켓 정보 확인
            listing = self.db.execute(
                select(MarketListing).where(MarketListing.product_id == product_id).limit(1)
            ).scalars().first()
            
            market_code = listing.market_code if listing else "COUPANG"
            
            # TODO: 카테고리 ID 연동 로직 추가 가능
            fee_rate = self._get_market_fee_rate(market_code)
            
            order_items = (
                self.db.execute(
                    select(OrderItem)
                    .join(Order, Order.id == OrderItem.order_id)
                    .where(OrderItem.product_id == product_id)
                    .where(Order.created_at >= period_start)
                    .where(Order.created_at <= period_end)
                )
                .scalars()
                .all()
            )
            
            for oi in order_items:
                total_actual_revenue += oi.total_price
                total_fees += oi.total_price * fee_rate
        
        # 2. 상품 구매 원가 계산 (옵션별 상세 원가 반영)
        order_items_for_cost = (
            self.db.execute(
                select(OrderItem)
                .join(Order, Order.id == OrderItem.order_id)
                .where(OrderItem.product_id == product_id)
                .where(Order.created_at >= period_start)
                .where(Order.created_at <= period_end)
            )
            .scalars()
            .all()
        )

        option_ids = [oi.product_option_id for oi in order_items_for_cost if oi.product_option_id]
        options_map = {}
        if option_ids:
            options = self.db.execute(
                select(ProductOption).where(ProductOption.id.in_(option_ids))
            ).scalars().all()
            options_map = {opt.id: opt for opt in options}
        
        total_cost = 0
        for oi in order_items_for_cost:
            opt = options_map.get(oi.product_option_id)
            cost_per_unit = opt.cost_price if opt else (product.cost_price if product else 0)
            total_cost += cost_per_unit * oi.quantity
            
        # 3. 부가세 계산 (매출의 10% 가정, 매입 부가세 공제 고려)
        vat_sales = total_actual_revenue * 0.1 / 1.1 # 포함 부가세
        vat_purchases = total_cost * 0.1
        net_vat = max(0, vat_sales - vat_purchases)
            
        actual_profit = total_actual_revenue - total_fees - total_cost - net_vat
        
        return {
            "actual_revenue": total_actual_revenue,
            "actual_fees": total_fees,
            "actual_vat": net_vat,
            "actual_profit": actual_profit,
            "net_settlement": total_actual_revenue - total_fees - net_vat
        }

    async def generate_strategic_insight(self, product_id: uuid.UUID) -> Dict[str, Any]:
        """
        AI 기반 제품 판매 전략 보고서를 생성합니다.
        """
        product = self.db.get(Product, product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")

        # 최근 4주 분석 데이터 가져오기
        analytics = (
            self.db.execute(
                select(SalesAnalytics)
                .where(SalesAnalytics.product_id == product_id)
                .order_by(SalesAnalytics.created_at.desc())
                .limit(4)
            )
            .scalars()
            .all()
        )

        if not analytics:
            # 분석 데이터가 없으면 즉시 분석 실행
            analytics_obj = await self.analyze_product_sales(product_id, period_type="weekly", period_count=4)
            analytics = [analytics_obj]

        # 성 성과 요약 구성
        latest = analytics[0]
        history_summary = "\n".join([
            f"- {a.period_start.date() if a.period_start else 'N/A'}: 주문 {a.total_orders}건, 매출 {a.total_revenue}원, 이익률 {a.avg_margin_rate:.1%}"
            for a in analytics
        ])

        prompt = f"""
        당신은 이커머스 매출 최적화 전문가입니다. 다음 상품의 최근 4주 성과를 분석하고 전략적 보고서를 작성하세요.

        상품명: {product.name}
        현재 상태: {product.status}
        
        최근 성과 이력:
        {history_summary}
        
        예상 다음 주 매출: {latest.predicted_revenue or '데이터 부족'}원
        성장률: {latest.revenue_growth_rate:.1%}
        시장 수요 점수: {latest.market_demand_score}/1.0

        반드시 다음 항목을 포함한 JSON 형식으로 응답하세요:
        1. "market_position": 현재 상품의 시장 위치 (라이징스타, 캐시카우, 골칫덩이, 개 등)
        2. "swot_analysis": {{ "strengths": [], "weaknesses": [], "opportunities": [], "threats": [] }}
        3. "pricing_strategy": 구체적인 가격 조정 제안 및 근거
        4. "action_plan": 향후 2주간 실행해야 할 우선순위 조치 3가지
        5. "expected_impact": 조치 실행 시 예상되는 매출 변화 (텍스트)
        """

        try:
            report = await self.ai_service.generate_json(prompt, provider="auto")
            return report
        except Exception as e:
            logger.error(f"Failed to generate strategic insight for {product_id}: {e}")
            raise
    
    def _calculate_growth_rate(
        self,
        product_id: uuid.UUID,
        period_type: str,
        current_period_start: datetime,
        current_stats: Dict[str, Any]
    ) -> Dict[str, float]:
        """전 대비 성장률 계산"""
        # 이전 기간 계산
        period_length = (datetime.now(timezone.utc) - current_period_start).days
        previous_period_start = current_period_start - timedelta(days=period_length)
        
        # 이전 기간 통계
        previous_stats = self._collect_order_stats(
            product_id, 
            previous_period_start, 
            current_period_start
        )
        
        # 성장률 계산
        order_growth_rate = 0.0
        if previous_stats["total_orders"] > 0:
            order_growth_rate = (
                (current_stats["total_orders"] - previous_stats["total_orders"]) 
                / previous_stats["total_orders"]
            )
        
        revenue_growth_rate = 0.0
        if previous_stats["total_revenue"] > 0:
            revenue_growth_rate = (
                (current_stats["total_revenue"] - previous_stats["total_revenue"]) 
                / previous_stats["total_revenue"]
            )
        
        return {
            "order_growth_rate": order_growth_rate,
            "revenue_growth_rate": revenue_growth_rate
        }
    
    async def _predict_future_sales(
        self,
        product: Product,
        current_stats: Dict[str, Any],
        period_type: str
    ) -> Dict[str, Any]:
        """
        AI 기반 미래 판매 예측
        
        Args:
            product: 제품 객체
            current_stats: 현재 기간 통계
            period_type: 기간 유형
        
        Returns:
            예측 결과 딕셔너리
        """
        try:
            # 과거 데이터 수집 (최근 4개 기간)
            historical_data = self._collect_historical_data(
                product.id, 
                period_type, 
                periods=4
            )
            
            # AI 프롬프트 구성
            prompt = self._build_prediction_prompt(
                product, 
                current_stats, 
                historical_data
            )
            
            # AI 예측
            prediction = await self.ai_service.generate_json(prompt, provider="auto")
            
            return {
                "predicted_orders": prediction.get("predicted_orders"),
                "predicted_revenue": prediction.get("predicted_revenue"),
                "confidence": prediction.get("confidence", 0.5)
            }
            
        except Exception as e:
            logger.warning(f"AI prediction failed for product {product.id}: {e}")
            # 간단한 선형 예측으로 대체
            return {
                "predicted_orders": current_stats["total_orders"],
                "predicted_revenue": current_stats["total_revenue"],
                "confidence": 0.3
            }
    
    def _collect_historical_data(
        self,
        product_id: uuid.UUID,
        period_type: str,
        periods: int
    ) -> List[Dict[str, Any]]:
        """과거 데이터 수집"""
        historical = []
        now = datetime.now(timezone.utc)
        
        for i in range(1, periods + 1):
            period_end = now - timedelta(days=i * 7 if period_type == "weekly" else i * 30)
            period_start = period_end - timedelta(days=7 if period_type == "weekly" else 30)
            
            stats = self._collect_order_stats(product_id, period_start, period_end)
            historical.append({
                "period": i,
                "orders": stats["total_orders"],
                "revenue": stats["total_revenue"]
            })
        
        return historical
    
    def _build_prediction_prompt(
        self,
        product: Product,
        current_stats: Dict[str, Any],
        historical_data: List[Dict[str, Any]]
    ) -> str:
        """예측 프롬프트 구성"""
        historical_str = "\n".join([
            f"Period {h['period']}: {h['orders']} orders, {h['revenue']} revenue"
            for h in historical_data
        ])
        
        return f"""
        Predict the next period's sales for this product:
        
        Product: {product.name}
        Current Period: {current_stats['total_orders']} orders, {current_stats['total_revenue']} revenue
        Average Margin Rate: {current_stats['avg_margin_rate']:.2%}
        
        Historical Data:
        {historical_str}
        
        Return ONLY a JSON object:
        {{
            "predicted_orders": int,
            "predicted_revenue": int,
            "confidence": float(0-1),
            "reasoning": "brief explanation"
        }}
        """
    
    async def _calculate_trend_scores(
        self,
        product: Product
    ) -> Dict[str, float]:
        """
        카테고리 및 시장 트렌드 점수 계산
        
        Args:
            product: 제품 객체
        
        Returns:
            트렌드 점수 딕셔너리
        """
        try:
            # 벤치마크 제품에서 카테고리 정보 추출
            category_trend_score = 0.5  # 기본값
            market_demand_score = 0.5  # 기본값
            
            if product.benchmark_product_id:
                benchmark = self.db.get(BenchmarkProduct, product.benchmark_product_id)
                if benchmark:
                    # 카테고리 기반 트렌드 점수 (리뷰 수, 평점 등 활용)
                    category_trend_score = min(1.0, benchmark.review_count / 1000.0)
                    category_trend_score = max(category_trend_score, benchmark.rating / 5.0)
                    
                    # 시장 수요 점수 (quality_score 활용)
                    market_demand_score = benchmark.quality_score
            
            return {
                "category_trend_score": category_trend_score,
                "market_demand_score": market_demand_score
            }
            
        except Exception as e:
            logger.warning(f"Trend score calculation failed: {e}")
            return {
                "category_trend_score": 0.5,
                "market_demand_score": 0.5
            }
    
    async def _generate_insights(
        self,
        product: Product,
        order_stats: Dict[str, Any],
        growth_stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        AI 기반 인사이트 및 추천 생성
        
        Args:
            product: 제품 객체
            order_stats: 주문 통계
            growth_stats: 성장률 통계
        
        Returns:
            인사이트 및 추천
        """
        try:
            prompt = f"""
            Analyze the sales performance of this product and provide insights:
            
            Product: {product.name}
            Cost Price: {product.cost_price}
            Selling Price: {product.selling_price}
            
            Sales Performance:
            - Total Orders: {order_stats['total_orders']}
            - Total Revenue: {order_stats['total_revenue']}
            - Total Profit: {order_stats['total_profit']}
            - Average Margin Rate: {order_stats['avg_margin_rate']:.2%}
            
            Growth:
            - Order Growth Rate: {growth_stats['order_growth_rate']:.2%}
            - Revenue Growth Rate: {growth_stats['revenue_growth_rate']:.2%}
            
            Return ONLY a JSON object:
            {{
                "trend_analysis": "brief trend summary",
                "insights": ["insight 1", "insight 2", "insight 3"],
                "recommendations": ["recommendation 1", "recommendation 2"]
            }}
            """
            
            result = await self.ai_service.generate_json(prompt, provider="auto")
            return {
                "trend_analysis": result.get("trend_analysis", ""),
                "insights": result.get("insights", []),
                "recommendations": result.get("recommendations", [])
            }
            
        except Exception as e:
            logger.warning(f"Insight generation failed: {e}")
            return {
                "trend_analysis": "Sales analysis completed",
                "insights": [
                    f"Total orders: {order_stats['total_orders']}",
                    f"Revenue: {order_stats['total_revenue']}",
                    f"Margin rate: {order_stats['avg_margin_rate']:.2%}"
                ],
                "recommendations": []
            }
    
    def get_top_performing_products(
        self,
        limit: int = 10,
        period_type: str = "weekly"
    ) -> List[Dict[str, Any]]:
        """
        상위 성과 제품 조회
        
        Args:
            limit: 조회할 제품 수
            period_type: 기간 유형
        
        Returns:
            상위 제품 목록
        """
        # 최근 분석 결과 조회
        subq = (
            select(
                SalesAnalytics.product_id,
                func.max(SalesAnalytics.created_at).label("latest_date")
            )
            .where(SalesAnalytics.period_type == period_type)
            .group_by(SalesAnalytics.product_id)
            .subquery()
        )
        
        analytics = (
            self.db.execute(
                select(SalesAnalytics)
                .join(subq, and_(
                    SalesAnalytics.product_id == subq.c.product_id,
                    SalesAnalytics.created_at == subq.c.latest_date
                ))
                .order_by(SalesAnalytics.total_revenue.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        
        results = []
        for a in analytics:
            product = self.db.get(Product, a.product_id)
            results.append({
                "product_id": str(a.product_id),
                "product_name": product.name if product else "Unknown",
                "total_orders": a.total_orders,
                "total_revenue": a.total_revenue,
                "total_profit": a.total_profit,
                "avg_margin_rate": a.avg_margin_rate,
                "order_growth_rate": a.order_growth_rate,
                "revenue_growth_rate": a.revenue_growth_rate,
                "predicted_orders": a.predicted_orders,
                "predicted_revenue": a.predicted_revenue
            })
        
        return results
    
    def get_low_performing_products(
        self,
        limit: int = 10,
        period_type: str = "weekly"
    ) -> List[Dict[str, Any]]:
        """
        저성과 제품 조회
        
        Args:
            limit: 조회할 제품 수
            period_type: 기간 유형
        
        Returns:
            저성과 제품 목록
        """
        # 최근 분석 결과 조회
        subq = (
            select(
                SalesAnalytics.product_id,
                func.max(SalesAnalytics.created_at).label("latest_date")
            )
            .where(SalesAnalytics.period_type == period_type)
            .group_by(SalesAnalytics.product_id)
            .subquery()
        )
        
        analytics = (
            self.db.execute(
                select(SalesAnalytics)
                .join(subq, and_(
                    SalesAnalytics.product_id == subq.c.product_id,
                    SalesAnalytics.created_at == subq.c.latest_date
                ))
                .where(SalesAnalytics.total_orders > 0)  # 최소 1건 이상 주문
                .order_by(SalesAnalytics.total_revenue.asc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        
        results = []
        for a in analytics:
            product = self.db.get(Product, a.product_id)
            results.append({
                "product_id": str(a.product_id),
                "product_name": product.name if product else "Unknown",
                "total_orders": a.total_orders,
                "total_revenue": a.total_revenue,
                "total_profit": a.total_profit,
                "avg_margin_rate": a.avg_margin_rate,
                "order_growth_rate": a.order_growth_rate,
                "revenue_growth_rate": a.revenue_growth_rate
            })
        
        return results

    async def get_option_performance(
        self,
        product_id: uuid.UUID,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        특정 상품의 옵션별 판매 성과를 분석합니다.
        
        Args:
            product_id: 제품 ID
            period_start: 시작일 (None일 경우 전체 기간)
            period_end: 종료일 (None일 경우 현재)
        
        Returns:
            옵션별 성과 목록
        """
        query = (
            select(OrderItem)
            .where(OrderItem.product_id == product_id)
        )
        
        if period_start:
            query = query.join(Order).where(Order.created_at >= period_start)
        if period_end:
            if not period_start:
                query = query.join(Order)
            query = query.where(Order.created_at <= period_end)
            
        items = self.db.execute(query).scalars().all()

        option_ids = [oi.product_option_id for oi in items if oi.product_option_id]
        options_map = {}
        if option_ids:
            options = self.db.execute(
                select(ProductOption).where(ProductOption.id.in_(option_ids))
            ).scalars().all()
            options_map = {opt.id: opt for opt in options}
        
        # 상품 정보 (백업 원가용)
        product = self.db.get(Product, product_id)
        base_cost = product.cost_price if product else 0
        
        performance = {}
        
        for oi in items:
            option_id = str(oi.product_option_id) if oi.product_option_id else "No Option"
            opt = options_map.get(oi.product_option_id)
            if option_id not in performance:
                performance[option_id] = {
                    "option_id": option_id,
                    "option_name": opt.option_name if opt else "Unknown",
                    "option_value": opt.option_value if opt else "단품",
                    "total_quantity": 0,
                    "total_revenue": 0,
                    "total_cost": 0,
                    "total_profit": 0,
                    "avg_margin_rate": 0.0
                }
            
            p = performance[option_id]
            p["total_quantity"] += oi.quantity
            p["total_revenue"] += oi.total_price
            
            cost_per_unit = opt.cost_price if opt else base_cost
            p["total_cost"] += cost_per_unit * oi.quantity
            
        # 후처리 (이익 및 이익률 계산)
        results = []
        for p in performance.values():
            p["total_profit"] = p["total_revenue"] - p["total_cost"]
            p["avg_margin_rate"] = (p["total_profit"] / p["total_revenue"]) if p["total_revenue"] > 0 else 0.0
            results.append(p)
            
        # 판매량 순으로 정렬
        results.sort(key=lambda x: x["total_quantity"], reverse=True)
        return results


def create_sales_analytics_service(db: Session) -> SalesAnalyticsService:
    """
    SalesAnalyticsService 인스턴스 생성 헬퍼
    
    Args:
        db: 데이터베이스 세션
    
    Returns:
        SalesAnalyticsService 인스턴스
    """
    return SalesAnalyticsService(db)
