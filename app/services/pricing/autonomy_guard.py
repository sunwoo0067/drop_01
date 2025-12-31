import uuid
import logging
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Optional

from app.models import AutonomyPolicy, AutonomyDecisionLog, PricingRecommendation, SystemSetting
from app.services.pricing.segment_resolver import SegmentResolver

logger = logging.getLogger(__name__)

class AutonomyGuard:
    """
    가격 변경 권고의 자율 집행 권한을 제어하는 가드 시스템입니다.
    """

    def __init__(self, db: Session):
        self.db = db
        self.resolver = SegmentResolver()

    def check_autonomy(self, recommendation: PricingRecommendation, metadata: dict) -> bool:
        """
        해당 권고안이 자동으로 집행될 수 있는지 자율 등급(Tier) 및 가드레일을 확인합니다.
        
        Args:
            recommendation: 분석된 가격 변경 권고 객체
            metadata: 세그먼트 식별을 위한 추가 정보 (vendor, channel, category_code, strategy_id, lifecycle_stage)
            
        Returns:
            bool: 자동 집행 승인 시 True, 수동 승인 대기 시 False
        """
        try:
            # 1. 전역 킬스위치 확인
            if self._is_global_kill_switch_on():
                self._log_decision(recommendation, "GLOBAL_KILL_SWITCH", "PENDING", ["Global Kill Switch is ON"])
                return False

            # 2. 세그먼트 식별 및 정책 조회
            segment_key = self.resolver.get_segment_key(metadata)
            
            stmt = select(AutonomyPolicy).where(AutonomyPolicy.segment_key == segment_key)
            policy = self.db.execute(stmt).scalars().first()

            # 정책이 없거나 동결(FROZEN) 상태면 수동 모드(Tier 0) 취급
            if not policy or policy.status == "FROZEN":
                reasons = ["Policy not found (Default Tier 0)" if not policy else "Segment is FROZEN"]
                self._log_decision(recommendation, segment_key if policy else "UNKNOWN", "PENDING", reasons, tier=0)
                return False

            # 3. 티어별 게이트 평가
            can_apply = False
            reasons = []
            
            logger.info(f"[AutonomyGuard] Checking Tier {policy.tier} for segment {segment_key}")
            
            if policy.tier == 0:
                reasons.append("Tier 0: Manual Approval Required")
            
            elif policy.tier == 1:
                # Tier 1 (Enforce Lite): 리스크 해소(역마진 등) 케이스만 자동
                risk_mitigation = self._is_risk_mitigation(recommendation)
                if risk_mitigation:
                    can_apply = True
                    reasons.append("Tier 1: Risk Mitigation (Auto)")
                else:
                    reasons.append("Tier 1: Normal Optimization (Manual)")
                logger.info(f"[AutonomyGuard] Tier 1 Check: is_risk={risk_mitigation}")
            
            elif policy.tier == 2:
                # Tier 2 (Auto High-Confidence): 고신뢰도 권고 + 리스크 케이스 자동
                threshold = (policy.config_override or {}).get("confidence_threshold", 0.97)
                is_high_conf = recommendation.confidence >= threshold
                is_risk = self._is_risk_mitigation(recommendation)
                
                if is_high_conf:
                    can_apply = True
                    reasons.append(f"Tier 2: High Confidence {recommendation.confidence} >= {threshold}")
                elif is_risk:
                    can_apply = True
                    reasons.append("Tier 2: Risk Mitigation (Auto)")
                else:
                    reasons.append(f"Tier 2: Low Confidence {recommendation.confidence} < {threshold}")
                logger.info(f"[AutonomyGuard] Tier 2 Check: is_high_conf={is_high_conf}, is_risk={is_risk}")
            
            elif policy.tier == 3:
                # Tier 3 (Full Auto): 모든 가드레일 통과 시 자동
                # 추후 튜닝 자동화 등 추가 조건 삽입 가능
                can_apply = True
                reasons.append("Tier 3: Full Autonomy (Applied)")

            decision = "APPLIED" if can_apply else "PENDING"
            self._log_decision(recommendation, segment_key, decision, reasons, tier=policy.tier)
            
            return can_apply

        except Exception as e:
            logger.error(f"[AutonomyGuard] Critical error during autonomy check: {e}")
            # 에러 발생 시 안전하게 수동(False) 반환
            return False

    def _is_global_kill_switch_on(self) -> bool:
        """전역 킬스위치 상태를 확인합니다."""
        stmt = select(SystemSetting).where(SystemSetting.key == "AUTONOMY_KILL_SWITCH")
        setting = self.db.execute(stmt).scalars().first()
        return bool(setting and setting.value.get("enabled"))

    def _is_risk_mitigation(self, reco: PricingRecommendation) -> bool:
        """기대 마진이 매우 낮거나 음수인 경우 리스크 대응으로 간주합니다."""
        # target_margin이 아닌 실측 expected_margin 기준
        if reco.expected_margin is not None and reco.expected_margin < 0.05:
            return True
        return False

    def _log_decision(self, reco: PricingRecommendation, segment_key: str, decision: str, reasons: list[str], tier: int = 0):
        """의사결정 이력을 DB에 기록합니다. (Flush만 호출하여 호출자 트랜잭션에 포함)"""
        log = AutonomyDecisionLog(
            recommendation_id=reco.id,
            segment_key=segment_key,
            tier_used=tier,
            decision=decision,
            confidence=reco.confidence,
            expected_margin=reco.expected_margin,
            reasons=reasons
        )
        self.db.add(log)
        self.db.flush()
        logger.info(f"[AutonomyGuard] Recommendation {reco.id} -> {decision} (Tier {tier}, Reasons: {reasons})")
