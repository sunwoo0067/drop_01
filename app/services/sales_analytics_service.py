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
    SalesAnalytics, Order, OrderItem, Product, 
    SourcingRecommendation, SupplierPerformance,
    SourcingCandidate, BenchmarkProduct
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
        
        total_orders = len(set(oi.order_id for oi in order_items))
        total_quantity = sum(oi.quantity for oi in order_items)
        total_revenue = sum(oi.total_price for oi in order_items)
        
        # 이익률 계산
        product = self.db.get(Product, product_id)
        if product:
            total_cost = product.cost_price * total_quantity
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


def create_sales_analytics_service(db: Session) -> SalesAnalyticsService:
    """
    SalesAnalyticsService 인스턴스 생성 헬퍼
    
    Args:
        db: 데이터베이스 세션
    
    Returns:
        SalesAnalyticsService 인스턴스
    """
    return SalesAnalyticsService(db)
