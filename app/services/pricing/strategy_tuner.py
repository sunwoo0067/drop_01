from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import TuningRecommendation, PricingStrategy
from app.services.pricing.drift_detector import DriftDetector

class StrategyTuner:
    """
    감지된 드리프트 신호를 바탕으로 전략 파라미터 최적화 권고안을 생성합니다.
    """
    def __init__(self, session: Session):
        self.session = session
        self.detector = DriftDetector(session)

    def run_tuning_cycle(self) -> list[TuningRecommendation]:
        """
        검사 주기를 실행하여 새로운 튜닝 권고안을 생성하고 저장합니다.
        """
        signals = self.detector.detect_drifts()
        new_recommendations = []
        
        for signal in signals:
            # 기존 PENDING 상태의 동일 유형 권고가 있는지 확인 (중복 생성 방지)
            existing = (
                self.session.query(TuningRecommendation)
                .filter_by(
                    strategy_id=signal["strategy_id"],
                    reason_code=signal["signal_type"],
                    status="PENDING"
                )
                .first()
            )
            if existing:
                continue
                
            strategy = self.session.get(PricingStrategy, signal["strategy_id"])
            if not strategy:
                continue

            # 권고 로직 산출
            suggested_config = {}
            if signal["signal_type"] == "SAFETY_SATURATION":
                # 거절율이 높으므로 변동폭 제한을 완화 (현재값 + 10%p)
                suggested_config["max_price_delta"] = round(strategy.max_price_delta + 0.10, 2)
                
            elif signal["signal_type"] == "MARGIN_DRIFT":
                # 기대 마진 괴리가 크므로 목표 마진 현실화 (실제 평균값으로 제안)
                suggested_config["target_margin"] = round(signal["current_value"], 3)

            if not suggested_config:
                continue

            reco = TuningRecommendation(
                strategy_id=signal["strategy_id"],
                suggested_config=suggested_config,
                reason_code=signal["signal_type"],
                reason_detail=signal["message"],
                status="PENDING"
            )
            self.session.add(reco)
            new_recommendations.append(reco)
            
        if new_recommendations:
            self.session.commit()
            
        return new_recommendations

    def apply_recommendation(self, recommendation_id: str) -> bool:
        """
        관리자가 승인한 권고안을 실제 전략에 반영합니다.
        """
        reco = self.session.get(TuningRecommendation, recommendation_id)
        if not reco or reco.status != "PENDING":
            return False
            
        strategy = self.session.get(PricingStrategy, reco.strategy_id)
        if not strategy:
            reco.status = "DISMISSED"
            self.session.commit()
            return False
            
        # 파라미터 업데이트
        for key, value in reco.suggested_config.items():
            if hasattr(strategy, key):
                setattr(strategy, key, value)
                
        reco.status = "APPLIED"
        reco.applied_at = datetime.now(timezone.utc)
        self.session.commit()
        return True
