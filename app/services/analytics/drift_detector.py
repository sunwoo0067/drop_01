import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import AdaptivePolicyEvent
from app.services.analytics.coupang_stats import CoupangAnalyticsService

logger = logging.getLogger(__name__)

class CoupangDriftDetectorService:
    """
    시즌성 종료 또는 환경 변화로 인한 성과 하락(Drift)을 감지하는 서비스입니다.
    """
    
    POLICY_VERSION = "1.3.0"
    DRIFT_THRESHOLD = -15.0  # AR이 15% 이상 하락 시 Drift로 간주
    MIN_TRIALS = 10         # 최소 10건 이상의 데이터가 있어야 분석 신뢰성 확보
    
    @staticmethod
    def analyze_category_drift(session: Session, category_code: str, days: int = 3) -> Dict[str, Any]:
        """
        특정 카테고리의 최근 윈도우와 이전 윈도우를 비교하여 Drift 여부를 판단합니다.
        """
        # 1. 현재 윈도우 (최근 3일)
        current_stats_list = CoupangAnalyticsService.get_category_approval_stats(session, days=days, offset_days=0)
        current = next((s for s in current_stats_list if s["category_code"] == category_code), None)
        
        # 2. 이전 윈도우 (3~6일 전)
        previous_stats_list = CoupangAnalyticsService.get_category_approval_stats(session, days=days, offset_days=days)
        previous = next((s for s in previous_stats_list if s["category_code"] == category_code), None)
        
        if not current or not previous:
            return {"is_drift": False, "reason": "Insufficient data in windows", "velocity": 0.0}
            
        cur_ar = current["approval_rate"]
        prev_ar = previous["approval_rate"]
        cur_trials = current["total_trials"]
        
        # 3. Velocity (변화량) 계산
        velocity = cur_ar - prev_ar
        
        is_drift = False
        severity = "NONE"
        
        if cur_trials >= CoupangDriftDetectorService.MIN_TRIALS:
            if velocity <= CoupangDriftDetectorService.DRIFT_THRESHOLD:
                is_drift = True
                severity = "WARNING" if velocity > -30 else "CRITICAL"
        
        result = {
            "category_code": category_code,
            "is_drift": is_drift,
            "severity": severity,
            "velocity": round(velocity, 2),
            "current_ar": cur_ar,
            "previous_ar": prev_ar,
            "current_trials": cur_trials,
            "days": days
        }
        
        if is_drift:
            CoupangDriftDetectorService._log_drift_event(session, result)
            
        return result

    @staticmethod
    def _log_drift_event(session: Session, drift_result: Dict[str, Any]):
        """
        Drift 감지 이벤트를 AdaptivePolicyEvent에 기록합니다.
        """
        # 중복 기록 방지 (최근 12시간 내 동일 카테고리 Drift 기록 확인)
        last_event = session.execute(
            select(AdaptivePolicyEvent)
            .where(AdaptivePolicyEvent.category_code == drift_result["category_code"])
            .where(AdaptivePolicyEvent.event_type == "DRIFT")
            .where(AdaptivePolicyEvent.created_at >= datetime.now(timezone.utc) - timedelta(hours=12))
        ).scalar_one_or_none()
        
        if last_event:
            return

        reason = f"성과 급락 감지 (AR: {drift_result['previous_ar']}% -> {drift_result['current_ar']}%, Velocity: {drift_result['velocity']})"
        
        event = AdaptivePolicyEvent(
            category_code=drift_result["category_code"],
            event_type="DRIFT",
            severity=drift_result["severity"],
            multiplier=0.8 if drift_result["severity"] == "WARNING" else 0.5,
            reason=reason,
            policy_version=CoupangDriftDetectorService.POLICY_VERSION,
            context=drift_result
        )
        session.add(event)
        session.commit()
        logger.info(f"Drift Detected: {drift_result['category_code']} - {reason}")
