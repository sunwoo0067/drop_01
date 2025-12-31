from sqlalchemy.orm import Session
from app.models import PricingStrategy
from app.services.pricing.strategy_monitor import StrategyMonitor

class DriftDetector:
    """
    전략의 유효성 저하(Drift) 및 가드레일 포화 상태를 감지합니다.
    """
    def __init__(self, session: Session):
        self.session = session
        self.monitor = StrategyMonitor(session)

    def detect_drifts(self, days: int = 7) -> list[dict]:
        """
        성과 지표를 분석하여 이상 징후(Signals) 목록을 반환합니다.
        """
        metrics = self.monitor.get_strategy_metrics(days=days)
        signals = []
        
        for m in metrics:
            strategy_id = m["strategy_id"]
            if not strategy_id:
                continue
                
            strategy = self.session.get(PricingStrategy, strategy_id)
            if not strategy:
                continue
                
            # 1. 가드레일 포화 감지 (Safety Saturation)
            # REJECTED 비율이 30%를 넘고, 표본이 5개 이상인 경우
            if m["recommendation_count"] >= 5:
                reject_rate = m["rejected_count"] / m["recommendation_count"]
                if reject_rate > 0.30:
                    signals.append({
                        "strategy_id": strategy_id,
                        "strategy_name": strategy.name,
                        "signal_type": "SAFETY_SATURATION",
                        "severity": "HIGH" if reject_rate > 0.50 else "MEDIUM",
                        "message": f"Rejected rate is {int(reject_rate*100)}%. Safeguard 'max_price_delta' might be too restrictive.",
                        "current_value": reject_rate,
                        "threshold": 0.30
                    })
                    
            # 2. 마진 드리프트 감지 (Margin Drift)
            # 여기서는 기대 마진과 실제 설정 마진의 차이를 봅니다 (주로 권고 생성 로직의 한계점 파악용)
            margin_drift = abs(m["avg_expected_margin"] - strategy.target_margin)
            if margin_drift > 0.05: # 5%p 이상의 차이
                signals.append({
                    "strategy_id": strategy_id,
                    "strategy_name": strategy.name,
                    "signal_type": "MARGIN_DRIFT",
                    "severity": "LOW",
                    "message": f"Average expected margin ({int(m['avg_expected_margin']*100)}%) deviates from target ({int(strategy.target_margin*100)}%).",
                    "current_value": m["avg_expected_margin"],
                    "target_value": strategy.target_margin
                })
                
        return signals
