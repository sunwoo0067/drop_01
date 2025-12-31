from datetime import datetime, timezone, timedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from typing import Dict, Any
import logging

from app.models import Order, OrderItem, Product, MarketListing, AdaptivePolicyEvent

logger = logging.getLogger(__name__)

class PolicySimulatorService:
    """
    정책 시뮬레이터 (v1.4.0 Final Slice)
    전략 변경(Pivot/Momentum) 시의 파급 효과를 미리 계산합니다.
    """

    @staticmethod
    def simulate_strategy_change(session: Session, drift_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        제안된 전략 변경(Pivot 등)의 예상 손익 및 리스크를 시뮬레이션합니다.
        """
        market_code = drift_data.get("market_code")
        market_label = market_code if market_code else "Global"
        
        should_pivot = drift_data.get("should_pivot", False)
        current_roi = drift_data.get("current_roi", 0.0)
        roi_velocity = drift_data.get("roi_velocity", 0.0)
        recent_penalties = drift_data.get("recent_penalties", 0)

        # 1. 예상 손실 방지액 (Avoided Loss) 계산
        # 만약 3일 전에 Pivot을 했다면 방지할 수 있었던 패널티/실패 비용 계산
        # (단순화: 패널티 1건당 약 5,000원의 운영 손실 가정)
        avoided_loss_est = recent_penalties * 5000 if should_pivot else 0
        
        # 2. 미래 ROI 예측 (Expected ROI)
        # 쿼터 축소 시 저수익 상품이 걸러지므로 ROI가 개선될 것으로 예측 (15% 개선 가정)
        expected_roi = current_roi * 1.15 if should_pivot else current_roi
        
        # 3. 리스크 프로파일 변화
        # Pivot 적용 시 리스크가 'Low'로 하락할 것으로 기대
        future_risk = "LOW" if should_pivot else ("HIGH" if recent_penalties > 30 else "MEDIUM")

        # 4. 비교 데이터 생성
        comparison = {
            "current": {
                "roi": current_roi,
                "risk": "HIGH" if should_pivot else "MEDIUM",
                "quota_usage": "100%"
            },
            "proposed": {
                "roi": round(expected_roi, 4),
                "risk": future_risk,
                "quota_usage": "50%" if should_pivot else "120%",
                "avoided_loss": avoided_loss_est
            }
        }

        # 5. 최종 리포트 및 액션 권고
        recommendation = "APPLY PIVOT" if should_pivot else "MAINTAIN / BOOST"
        
        return {
            "market_code": market_code,
            "strategy_name": f"{market_label} Sourcing Strategy",
            "simulation_timestamp": datetime.now(timezone.utc).isoformat(),
            "recommendation": recommendation,
            "comparison": comparison,
            "justification": drift_data.get("message", "Strategy is healthy."),
            "impact_summary": f"{market_label} Pivot 적용 시 예상 ROI {expected_roi:.2f}, 패널티 {recent_penalties}건 억제 효과 기대." if should_pivot else f"{market_label} 현재 전략 유지 시 안정적 수익 확보 기대."
        }
