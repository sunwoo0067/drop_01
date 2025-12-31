import uuid
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models import PricingExperiment, PricingSettings
from app.services.pricing.analyzer import ExperimentAnalyzer

class LearningLoop:
    def __init__(self, db: Session):
        self.db = db

    def finalize_and_optimize(self, experiment_id: uuid.UUID) -> dict:
        """
        실험을 종료하고 성능이 우수한 그룹의 정책을 전역 설정에 반영합니다.
        """
        # 1. 실험 정보 로드
        stmt = select(PricingExperiment).where(PricingExperiment.id == experiment_id)
        exp = self.db.execute(stmt).scalars().first()
        if not exp or exp.status != "ACTIVE":
            return {"success": False, "message": "Experiment not found or already finished"}

        # 2. 결과 분석
        analyzer = ExperimentAnalyzer(self.db)
        results = analyzer.get_results(experiment_id)
        
        # 3. 결정 로직 (단순화: TEST 그룹의 Applied Rate가 CONTROL보다 높거나 Margin이 좋은 경우 우승)
        test = results.get("TEST", {})
        control = results.get("CONTROL", {})
        
        test_total = test.get("total_recommendations", 0)
        control_total = control.get("total_recommendations", 0)
        
        if test_total == 0 or control_total == 0:
            return {"success": False, "message": "Insufficient data for evaluation"}

        test_applied_rate = test.get("applied_count", 0) / test_total
        control_applied_rate = control.get("applied_count", 0) / control_total
        
        test_avg_margin = test.get("avg_margin", 0.0)
        control_avg_margin = control.get("avg_margin", 0.0)
        
        # TEST 대안이 집행률이 더 높거나(더 많은 자동화) 마진이 더 좋은 경우 
        is_winner = (test_applied_rate > control_applied_rate) or (test_avg_margin > control_avg_margin)

        # 4. 정책 반영 (활성 중인 모든 계정에 실험군 정책을 기본으로 전파)
        if is_winner and exp.config_variant:
            stmt_settings = select(PricingSettings)
            settings_list = self.db.execute(stmt_settings).scalars().all()
            for s in settings_list:
                for key, val in exp.config_variant.items():
                    if hasattr(s, key):
                        setattr(s, key, val)
        
        # 5. 상태 업데이트
        exp.status = "APPLIED" if is_winner else "FINISHED"
        exp.metrics_summary = results
        self.db.commit()

        return {
            "success": True,
            "winner": "TEST" if is_winner else "CONTROL",
            "results": results
        }
