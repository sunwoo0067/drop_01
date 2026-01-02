"""
상품 가공 자율성 가드 시스템

ProcessingService와 함께 사용하여 상품 가공(이름/이미지/설명/프리미엄 이미지)의
자율 집행 권한을 제어합니다.
"""
import logging
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Optional

from app.models import AutonomyPolicy, AutonomyDecisionLog, Product
from app.services.pricing.segment_resolver import SegmentResolver


logger = logging.getLogger(__name__)


class ProcessingAutonomyGuard:
    """
    상품 가공의 자율 집행 권한을 제어하는 가드 시스템입니다.
    """

    # 가공 타입별 우선순위 (높을수록 위험도 높음)
    PROCESSING_PRIORITY = {
        "NAME": 1,           # 상품명 최적화 - 저위험
        "KEYWORDS": 1,        # 키워드 추출 - 저위험
        "DESCRIPTION": 2,      # 상세 설명 - 중위험
        "IMAGE": 2,           # 이미지 처리 - 중위험
        "PREMIUM_IMAGE": 3,    # 프리미엄 이미지 생성 - 고위험 (비용 발생)
        "FULL_BRANDING": 3,    # 전체 브랜딩 - 고위험
    }

    def __init__(self, db: Session):
        self.db = db
        self.resolver = SegmentResolver()

    def check_processing_autonomy(
        self,
        product: Product,
        processing_type: str,
        metadata: Optional[dict] = None
    ) -> tuple[bool, list[str], int]:
        """
        해당 상품 가공이 자동으로 실행될 수 있는지 자율 등급(Tier) 및 가드레일을 확인합니다.

        Args:
            product: 가공 대상 상품
            processing_type: 가공 유형 (NAME, IMAGE, PREMIUM_IMAGE, DESCRIPTION, FULL_BRANDING)
            metadata: 세그먼트 식별을 위한 추가 정보 (vendor, channel, category_code, strategy_id)

        Returns:
            tuple[bool, list[str], int]: 
                - 자동 집행 승인 여부
                - 사유 목록
                - 사용된 티어 레벨
        """
        try:
            # 1. 전역 킬스위치 확인
            if self._is_global_kill_switch_on():
                reasons = ["전역 킬스위치 활성화로 인한 수동 승인 대기"]
                logger.warning(f"[ProcessingAutonomyGuard] 전역 킬스위치 활성화 (상품 ID: {product.id})")
                self._log_decision(
                    product_id=str(product.id),
                    processing_type=processing_type,
                    decision="PENDING",
                    reasons=reasons,
                    tier=0
                )
                return False, reasons, 0

            # 2. 세그먼트 식별 및 정책 조회
            segment_key = self._get_segment_key(product, metadata)
            
            stmt = select(AutonomyPolicy).where(AutonomyPolicy.segment_key == segment_key)
            policy = self.db.execute(stmt).scalars().first()

            # 정책이 없거나 동결(FROZEN) 상태면 수동 모드(Tier 0) 취급
            if not policy or policy.status == "FROZEN":
                reasons = ["자율성 정책 없음 (기본 Tier 0 - 수동 승인)"] if not policy else ["세그먼트 동결 상태 (Tier 0 - 수동 승인)"]
                self._log_decision(
                    product_id=str(product.id),
                    processing_type=processing_type,
                    decision="PENDING",
                    reasons=reasons,
                    tier=0
                )
                return False, reasons, 0

            # 3. 티어별 게이트 평가
            can_apply = False
            reasons = []
            
            processing_priority = self.PROCESSING_PRIORITY.get(processing_type, 2)
            
            logger.info(f"[ProcessingAutonomyGuard] Tier {policy.tier} 체크 (세그먼트: {segment_key}, 가공 타입: {processing_type}, 우선순위: {processing_priority})")

            if policy.tier == 0:
                reasons.append("Tier 0: 수동 승인 필수")

            elif policy.tier == 1:
                # Tier 1 (Enforce Lite): 저위험 가공만 자동
                if processing_priority <= 1:
                    can_apply = True
                    reasons.append(f"Tier 1: 저위험 가공 ({processing_type}) 자동 승인")
                else:
                    reasons.append(f"Tier 1: 고위험 가공 ({processing_type}) 수동 승인 필요")
                logger.info(f"[ProcessingAutonomyGuard] Tier 1 체크: can_apply={can_apply}, priority={processing_priority}")

            elif policy.tier == 2:
                # Tier 2 (Auto High-Confidence): STEP_2 이상 상품만 고위험 가공 자동
                is_high_stage = product.lifecycle_stage in ["STEP_2", "STEP_3"]
                
                if is_high_stage:
                    can_apply = True
                    reasons.append(f"Tier 2: 승격 상품 ({product.lifecycle_stage}) {processing_type} 자동 승인")
                elif processing_priority <= 1:
                    can_apply = True
                    reasons.append(f"Tier 2: 저위험 가공 ({processing_type}) 자동 승인")
                else:
                    reasons.append(f"Tier 2: STEP_1 상품의 고위험 가공 ({processing_type}) 수동 승인 필요")
                
                logger.info(f"[ProcessingAutonomyGuard] Tier 2 체크: is_high_stage={is_high_stage}, can_apply={can_apply}")

            elif policy.tier == 3:
                # Tier 3 (Full Auto): 모든 가공 자동 (프리미엄 이미지 포함)
                can_apply = True
                reasons.append(f"Tier 3: 완전 자율 {processing_type} 승인")

            decision = "APPLIED" if can_apply else "PENDING"
            self._log_decision(
                product_id=str(product.id),
                processing_type=processing_type,
                decision=decision,
                reasons=reasons,
                tier=policy.tier
            )

            logger.info(f"[ProcessingAutonomyGuard] 상품 {product.id} {processing_type} -> {decision} (Tier {policy.tier}, 사유: {reasons})")
            return can_apply, reasons, policy.tier

        except Exception as e:
            logger.error(f"[ProcessingAutonomyGuard] 자율성 체크 중 치명적 오류 발생: {e}", exc_info=True)
            # 에러 발생 시 안전하게 수동(False) 반환
            return False, [f"시스템 오류로 인한 수동 승인: {str(e)}"], 0

    def _is_global_kill_switch_on(self) -> bool:
        """전역 킬스위치 상태를 확인합니다."""
        from app.models import SystemSetting
        
        stmt = select(SystemSetting).where(SystemSetting.key == "PROCESSING_AUTONOMY_KILL_SWITCH")
        setting = self.db.execute(stmt).scalars().first()
        return bool(setting and setting.value.get("enabled"))

    def _get_segment_key(self, product: Product, metadata: Optional[dict]) -> str:
        """세그먼트 키를 생성합니다."""
        segment_metadata = self.resolver.resolve_segment_metadata(
            vendor=metadata.get("vendor", "ownerclan") if metadata else "ownerclan",
            channel=metadata.get("channel", "COUPANG") if metadata else "COUPANG",
            category_code=metadata.get("category_code") if metadata else None,
            strategy_id=product.strategy_id,
            lifecycle_stage=product.lifecycle_stage
        )
        return self.resolver.get_segment_key(segment_metadata)

    def _log_decision(
        self,
        product_id: str,
        processing_type: str,
        decision: str,
        reasons: list[str],
        tier: int = 0
    ):
        """
        의사결정 이력을 DB에 기록합니다.
        
        참고: ProcessingDecisionLog 모델이 별도로 필요할 수 있으나,
        현재는 AutonomyDecisionLog를 재사용하거나 별도 로그를 남길 수 있습니다.
        """
        # 현재 AutonomyDecisionLog는 PricingRecommendation 기반이라,
        # 상품 가공용 별도 테이블이 필요할 수 있습니다.
        # 여기서는 우선 로그만 출력합니다.
        
        log_data = {
            "product_id": product_id,
            "processing_type": processing_type,
            "decision": decision,
            "tier": tier,
            "reasons": reasons
        }
        logger.info(f"[ProcessingAutonomyGuard] 가공 의사결정 기록: {log_data}")


class ProcessingDecisionEvent:
    """
    상품 가공 의사결정 이벤트를 나타냅니다.
    추후 별도 테이블로 확장할 때 사용합니다.
    """
    def __init__(
        self,
        product_id: str,
        processing_type: str,
        decision: str,
        tier: int,
        reasons: list[str],
        metadata: dict | None = None
    ):
        self.product_id = product_id
        self.processing_type = processing_type
        self.decision = decision  # APPLIED, PENDING, REJECTED
        self.tier = tier
        self.reasons = reasons
        self.metadata = metadata or {}
