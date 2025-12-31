import uuid
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from app.models import PricingRecommendation

class ExperimentAnalyzer:
    def __init__(self, db: Session):
        self.db = db

    def get_results(self, experiment_id: uuid.UUID) -> dict:
        """
        실험 그룹별 성과 지표를 집계하여 반환합니다.
        """
        results = {}
        
        # 그룹별 권고 총량 및 상태 집계
        stmt = (
            select(
                PricingRecommendation.experiment_group,
                PricingRecommendation.status,
                func.count(PricingRecommendation.id).label("count"),
                func.avg(PricingRecommendation.expected_margin).label("avg_margin")
            )
            .where(PricingRecommendation.experiment_id == experiment_id)
            .group_by(PricingRecommendation.experiment_group, PricingRecommendation.status)
        )
        
        rows = self.db.execute(stmt).all()
        for row in rows:
            group = row.experiment_group
            if not group: continue
            
            if group not in results:
                results[group] = {
                    "total_recommendations": 0,
                    "applied_count": 0,
                    "rejected_count": 0,
                    "avg_margin": 0.0,
                    "status_breakdown": {}
                }
            
            results[group]["status_breakdown"][row.status] = row.count
            results[group]["total_recommendations"] += row.count
            if row.status == "APPLIED":
                results[group]["applied_count"] += row.count
            elif row.status == "REJECTED":
                results[group]["rejected_count"] += row.count
            
            # 단순 평균 가중치 합산 (평균 마진 업데이트)
            total = results[group]["total_recommendations"]
            old_count = total - row.count
            results[group]["avg_margin"] = (results[group]["avg_margin"] * old_count + (row.avg_margin or 0.0) * row.count) / total

        return results
