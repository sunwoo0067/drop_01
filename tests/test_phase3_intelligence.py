import asyncio
import uuid
import logging
from sqlalchemy import select
from app.db import get_session
from app.models import Product, Order, OrderItem, SalesAnalytics, ProductOption
from app.services.sales_analytics_service import SalesAnalyticsService
from app.services.sourcing_recommendation_service import SourcingRecommendationService
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_phase3_intelligence():
    # 1. 테스트용 세션 생성
    session_gen = get_session()
    db = next(session_gen)

    try:
        # 2. 테스트 상품 조회 (가장 최근 상품 하나 선택)
        product = db.execute(select(Product).limit(1)).scalar()
        if not product:
            logger.error("No products found for testing")
            return

        logger.info(f"Testing with product: {product.name} ({product.id})")

        # 3. SalesAnalyticsService 테스트 (정밀 수익 및 AI 전략)
        analytics_service = SalesAnalyticsService(db)
        
        # 3-1. 정밀 수익 분석 테스트
        period_end = datetime.now(timezone.utc)
        period_start = period_end - timedelta(days=30)
        
        stats = analytics_service._collect_actual_market_stats(
            product.id, period_start, period_end
        )
        logger.info(f"Fiscal Stats: {stats}")
        assert "actual_fees" in stats
        assert "actual_vat" in stats
        assert "actual_profit" in stats

        # 3-2. AI 전략 보고서 생성 테스트
        logger.info("Generating AI Strategic Insight...")
        report = await analytics_service.generate_strategic_insight(product.id)
        logger.info(f"AI Strategic Report: {report}")
        assert "market_position" in report
        assert "swot_analysis" in report
        assert "pricing_strategy" in report

        # 4. SourcingRecommendationService 테스트 (최적 가격 예측)
        recomm_service = SourcingRecommendationService(db)
        
        logger.info("Predicting Optimal Price...")
        price_prediction = await recomm_service.predict_optimal_price(product.id)
        logger.info(f"Optimal Price Prediction: {price_prediction}")
        assert "optimal_price" in price_prediction
        assert "strategy" in price_prediction

        logger.info("Phase 3 Intelligence Verification Successful!")

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_phase3_intelligence())
