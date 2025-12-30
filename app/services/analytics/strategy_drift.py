from datetime import datetime, timezone, timedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import logging

from app.models import Order, OrderItem, Product, MarketListing, AdaptivePolicyEvent

logger = logging.getLogger(__name__)

class StrategyDriftDetector:
    """
    메타 레벨 전략 감지기 (v1.4.0)
    개별 카테고리를 넘어 시스템 전체 전략의 유효성을 판단합니다.
    """

    @staticmethod
    def analyze_global_strategy_health(session: Session, days: int = 14) -> Dict[str, Any]:
        """
        시스템 전체의 전략적 건강 상태를 분석합니다.
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        mid_point = datetime.now(timezone.utc) - timedelta(days=days // 2)

        # 1. Global ROI (최근 14일)
        # 14일 전 ~ 7일 전 vs 7일 전 ~ 현재 비교
        def get_period_roi(start, end):
            query = (
                select(
                    func.sum(OrderItem.total_price).label("revenue"),
                    func.sum(OrderItem.quantity * Product.cost_price).label("cost")
                )
                .join(Product, OrderItem.product_id == Product.id)
                .where(OrderItem.created_at >= start)
                .where(OrderItem.created_at < end)
            )
            res = session.execute(query).one()
            rev = res.revenue or 0
            cost = res.cost or 0
            return (rev - cost) / cost if cost > 0 else 0.0

        current_roi = get_period_roi(mid_point, datetime.now(timezone.utc))
        previous_roi = get_period_roi(start_date, mid_point)
        
        roi_velocity = current_roi - previous_roi

        # 2. Risk Exposure (Suspension/Denial Rate)
        # 마켓 등록 거절이나 상품 정지 빈도 분석 (v1.2.0의 AdaptivePolicyEvent 활용)
        risk_query = (
            select(func.count(AdaptivePolicyEvent.id))
            .where(AdaptivePolicyEvent.event_type == "PENALTY")
            .where(AdaptivePolicyEvent.created_at >= mid_point)
        )
        recent_penalties = session.execute(risk_query).scalar() or 0

        # 3. Strategy Pivot Signal
        # ROI가 급격히 하락하거나 패널티가 급증하는 경우 전략 폐기 신호 생성
        should_pivot = False
        message = "Strategy Healthy"
        severity = "INFO"

        if current_roi < 0.1 and roi_velocity < -0.05:
            should_pivot = True
            message = "CRITICAL: Strategy ROI collapse detected. Pivot recommended."
            severity = "CRITICAL"
        elif roi_velocity < -0.1:
            should_pivot = True
            message = "WARNING: Rapid ROI decay. Strategy effectiveness fading."
            severity = "WARNING"
        elif recent_penalties > 50: # 임계값 예시
            should_pivot = True
            message = "CRITICAL: Market risk overload. Scaling down strategy."
            severity = "CRITICAL"

        return {
            "current_roi": round(current_roi, 4),
            "roi_velocity": round(roi_velocity, 4),
            "recent_penalties": recent_penalties,
            "should_pivot": should_pivot,
            "message": message,
            "severity": severity,
            "timestamp": datetime.now(timezone.utc)
        }
