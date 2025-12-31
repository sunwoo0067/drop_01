from datetime import datetime, timedelta, timezone
import logging
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models import AutonomyPolicy, AutonomyDecisionLog, PricingRecommendation

logger = logging.getLogger(__name__)

class AutonomyTuner:
    """
    자율 정책의 성과 지표를 분석하여 티어 승격(Promotion) 및 강등(Demotion)을 제안하거나 집행합니다.
    """
    
    def __init__(self, db: Session):
        self.db = db

    def run_evolution_cycle(self, days: int = 14) -> list[dict]:
        """
        주기적으로 실행되어 세그먼트별 자율성 상태를 진단하고 최적화합니다.
        """
        stmt = select(AutonomyPolicy).where(AutonomyPolicy.status == "ACTIVE")
        policies = self.db.execute(stmt).scalars().all()
        
        results = []
        for policy in policies:
            # 1. 즉시 강등 조건 확인 (Near-realtime 시그널)
            demotion_reason = self._check_demotion_trigger(policy)
            if demotion_reason:
                self._apply_demotion(policy, demotion_reason)
                results.append({"segment": policy.segment_key, "action": "DEMOTE", "reason": demotion_reason})
                continue
                
            # 2. 승격 조건 확인 (Long-term 안정성 지표)
            if policy.tier < 3:
                promotion_reason = self._check_promotion_trigger(policy, days)
                if promotion_reason:
                    # 관리자 대시보드에서 검토할 수 있도록 추천 형태로 반환
                    results.append({"segment": policy.segment_key, "action": "PROMOTION_RECOMMENDED", "reason": promotion_reason})
        
        return results

    def _check_demotion_trigger(self, policy: AutonomyPolicy) -> str | None:
        """
        최근 24시간 내 사고 지표(높은 반려율, 마진 손실 등) 발생 시 강등 여부를 판단합니다.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        
        # 해당 세그먼트의 최근 집행 결과 조회
        stmt = select(
            func.count(AutonomyDecisionLog.id).label("total"),
            func.sum(func.cast(AutonomyDecisionLog.decision == "REJECTED", func.int)).label("rejected")
        ).where(
            AutonomyDecisionLog.segment_key == policy.segment_key,
            AutonomyDecisionLog.created_at >= since
        )
        
        row = self.db.execute(stmt).first()
        if row and row.total >= 10:
            rejection_rate = row.rejected / row.total
            # 반려율이 50%를 넘으면 시스템이 현재 시장 상황에 적응하지 못하고 있다고 판단하여 강등
            if rejection_rate > 0.5:
                return f"Critical Rejection Rate: {rejection_rate:.1%} in last 24h"
                
        return None

    def _check_promotion_trigger(self, policy: AutonomyPolicy, days: int) -> str | None:
        """
        지정된 기간 동안 안정적인 성과를 유지했는지 확인하여 승격 가능성을 진단합니다.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)
        
        # 세그먼트별 집행 성공률 및 평균 신뢰도 통계
        stmt = select(
            func.count(AutonomyDecisionLog.id).label("total"),
            func.sum(func.cast(AutonomyDecisionLog.decision == "APPLIED", func.int)).label("applied"),
            func.avg(AutonomyDecisionLog.confidence).label("avg_conf")
        ).where(
            AutonomyDecisionLog.segment_key == policy.segment_key,
            AutonomyDecisionLog.created_at >= since
        )
        
        row = self.db.execute(stmt).first()
        if not row or row.total < 30: # 데이터 모수 부족 시 승격 유보
            return None
            
        success_rate = row.applied / row.total
        
        # 승격 기준 예시: 성공률 90% 이상 + 평균 신뢰도 0.96 이상
        if success_rate >= 0.90 and row.avg_conf >= 0.96:
            return f"Stable performance for {days} days: Success Rate {success_rate:.1%}, Avg Conf {row.avg_conf:.2f}"
            
        return None

    def _apply_demotion(self, policy: AutonomyPolicy, reason: str):
        """즉시 Tier 0으로 강등하고 동결 처리합니다."""
        logger.warning(f"[AutonomyTuner] Demoting segment {policy.segment_key} to Tier 0: {reason}")
        policy.tier = 0
        policy.status = "FROZEN" # 관리자가 원인 파악 후 해제할 때까지 동결
        self.db.commit()
