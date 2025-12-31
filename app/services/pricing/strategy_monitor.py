import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from app.models import PricingStrategy, PricingRecommendation

class StrategyMonitor:
    """
    전략별 성과 지표(KPI)를 집계하고 모니터링합니다.
    """
    def __init__(self, session: Session):
        self.session = session

    def get_strategy_metrics(self, days: int = 7) -> list[dict]:
        """
        최근 n일간의 전략별 성과 메트릭을 반환합니다.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)
        
        # 1. 모든 전략 조회
        strategies = self.session.query(PricingStrategy).all()
        
        # 2. 전략별 추천 통계 집계
        # SELECT strategy_id, status, count(*), avg(expected_margin)
        # FROM pricing_recommendations 
        # WHERE created_at >= since
        # GROUP BY strategy_id, status
        
        stats_query = (
            self.session.query(
                PricingRecommendation.strategy_id,
                PricingRecommendation.status,
                func.count(PricingRecommendation.id).label("count"),
                func.avg(PricingRecommendation.expected_margin).label("avg_expected_margin")
            )
            .filter(PricingRecommendation.created_at >= since)
            .group_by(PricingRecommendation.strategy_id, PricingRecommendation.status)
            .all()
        )
        
        # 결과를 전략 ID별로 그룹화
        results_map = {s.id: {
            "strategy_id": s.id,
            "strategy_name": s.name,
            "recommendation_count": 0,
            "applied_count": 0,
            "rejected_count": 0,
            "pending_count": 0,
            "avg_expected_margin": 0.0,
            "margin_sum": 0.0,
            "margin_count": 0
        } for s in strategies}
        
        # 데이터가 없는 (None) 경우에 대한 기본 항목 추가 (fallback/default 전략 등)
        results_map[None] = {
            "strategy_id": None,
            "strategy_name": "DEFAULT",
            "recommendation_count": 0,
            "applied_count": 0,
            "rejected_count": 0,
            "pending_count": 0,
            "avg_expected_margin": 0.0,
            "margin_sum": 0.0,
            "margin_count": 0
        }
        
        for strat_id, status, count, avg_margin in stats_query:
            if strat_id not in results_map:
                continue # 삭제된 전략이나 알 수 없는 ID
                
            entry = results_map[strat_id]
            entry["recommendation_count"] += count
            
            if status == "APPLIED":
                entry["applied_count"] = count
            elif status == "REJECTED":
                entry["rejected_count"] = count
            elif status == "PENDING":
                entry["pending_count"] = count
                
            if avg_margin is not None:
                entry["margin_sum"] += (avg_margin * count)
                entry["margin_count"] += count
        
        # 최종 마진 평균 계산 및 정리
        final_metrics = []
        for strat_id, data in results_map.items():
            if data["recommendation_count"] > 0:
                if data["margin_count"] > 0:
                    data["avg_expected_margin"] = round(data["margin_sum"] / data["margin_count"], 4)
                
                # 필요 없는 보조 필드 제거
                del data["margin_sum"]
                del data["margin_count"]
                final_metrics.append(data)
                
        return final_metrics
