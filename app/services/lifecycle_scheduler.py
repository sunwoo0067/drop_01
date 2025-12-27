"""
라이프사이클 스케줄러

상품 라이프사이클 단계 전환을 자동화하는 스케줄러입니다.
매일 정해진 시간에 전환 조건을 체크하고, 조건에 맞는 상품을 자동으로 전환합니다.
"""

import logging
from datetime import datetime
from typing import Dict, Optional
import uuid

from app.db import SessionLocal
from app.models import OrchestrationEvent
from app.services.product_lifecycle_service import ProductLifecycleService

logger = logging.getLogger(__name__)


class LifecycleScheduler:
    """
    라이프사이클 스케줄러
    
    기능:
    - 매일 정해진 시간에 전환 조건 체크
    - STEP 1 → 2 자동 전환
    - STEP 2 → 3 자동 전환
    - 전환 이력 및 이벤트 기록
    """

    def __init__(self):
        self.is_running = False

    async def check_and_transition_all(
        self,
        dry_run: bool = True,
        auto_transition: bool = True
    ) -> Dict[str, any]:
        """
        모든 상품의 전환 조건 체크 및 자동 전환
        
        Args:
            dry_run: True면 전환 조건만 체크, False면 실제 전환 수행
            auto_transition: 자동 전환 여부 플래그 (이력에 기록됨)
            
        Returns:
            {
                "dry_run": bool,
                "step1_to_step2": {"checked": 100, "transitioned": 10, "candidates": [...]},
                "step2_to_step3": {"checked": 50, "transitioned": 5, "candidates": [...]},
                "total_transitioned": 15,
                "execution_time_seconds": 5.2,
                "errors": []
            }
        """
        start_time = datetime.now()
        
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}라이프사이클 전환 체크 시작")

        results = {
            "dry_run": dry_run,
            "step1_to_step2": {"checked": 0, "transitioned": 0, "candidates": []},
            "step2_to_step3": {"checked": 0, "transitioned": 0, "candidates": []},
            "total_transitioned": 0,
            "execution_time_seconds": 0,
            "errors": []
        }

        try:
            with SessionLocal() as session:
                lifecycle_service = ProductLifecycleService(session)

                # STEP 1 → 2 체크
                logger.info("STEP 1 → 2 전환 조건 체크 중...")
                step1_result = await self._check_step1_to_step2(
                    lifecycle_service,
                    dry_run=dry_run,
                    auto_transition=auto_transition
                )
                results["step1_to_step2"] = step1_result

                # STEP 2 → 3 체크
                logger.info("STEP 2 → 3 전환 조건 체크 중...")
                step2_result = await self._check_step2_to_step3(
                    lifecycle_service,
                    dry_run=dry_run,
                    auto_transition=auto_transition
                )
                results["step2_to_step3"] = step2_result

                # 총 전환 수 계산
                results["total_transitioned"] = (
                    results["step1_to_step2"]["transitioned"] +
                    results["step2_to_step3"]["transitioned"]
                )

                # 실행 시간 계산
                execution_time = (datetime.now() - start_time).total_seconds()
                results["execution_time_seconds"] = round(execution_time, 2)

                # 오케스트레이션 이벤트 기록
                await self._record_orchestration_event(session, results, dry_run=dry_run)

            logger.info(f"{'[DRY RUN] ' if dry_run else ''}라이프사이클 전환 체크 완료: "
                       f"전환 {results['total_transitioned']}건, "
                       f"실행 시간 {results['execution_time_seconds']}초")

        except Exception as e:
            logger.error(f"라이프사이클 전환 체크 중 오류: {e}", exc_info=True)
            results["errors"].append(str(e))

        return results

    async def _check_step1_to_step2(
        self,
        lifecycle_service: ProductLifecycleService,
        dry_run: bool,
        auto_transition: bool
    ) -> Dict[str, any]:
        """STEP 1 → 2 전환 체크"""
        step1_candidates = lifecycle_service.get_transition_candidates("STEP_1")
        
        result = {
            "checked": len(step1_candidates),
            "transitioned": 0,
            "candidates": step1_candidates
        }

        if not dry_run and auto_transition:
            for candidate in step1_candidates:
                try:
                    product_id = uuid.UUID(candidate["product_id"])
                    lifecycle_service.transition_to_step2(
                        product_id,
                        reason="자동 전환: 판매 ≥ 1 AND CTR ≥ 2% 기준 충족",
                        auto_transition=True
                    )
                    result["transitioned"] += 1
                    logger.info(f"STEP 1 → 2 자동 전환: {candidate['name']} ({product_id})")
                except Exception as e:
                    logger.error(f"STEP 1→2 전환 실패 (product={candidate['product_id']}): {e}")

        return result

    async def _check_step2_to_step3(
        self,
        lifecycle_service: ProductLifecycleService,
        dry_run: bool,
        auto_transition: bool
    ) -> Dict[str, any]:
        """STEP 2 → 3 전환 체크"""
        step2_candidates = lifecycle_service.get_transition_candidates("STEP_2")
        
        result = {
            "checked": len(step2_candidates),
            "transitioned": 0,
            "candidates": step2_candidates
        }

        if not dry_run and auto_transition:
            for candidate in step2_candidates:
                try:
                    product_id = uuid.UUID(candidate["product_id"])
                    lifecycle_service.transition_to_step3(
                        product_id,
                        reason="자동 전환: 판매 ≥ 5 AND 재구매 ≥ 1 기준 충족",
                        auto_transition=True
                    )
                    result["transitioned"] += 1
                    logger.info(f"STEP 2 → 3 자동 전환: {candidate['name']} ({product_id})")
                except Exception as e:
                    logger.error(f"STEP 2→3 전환 실패 (product={candidate['product_id']}): {e}")

        return result

    async def _record_orchestration_event(
        self,
        session,
        results: Dict[str, any],
        dry_run: bool
    ):
        """오케스트레이션 이벤트 기록"""
        try:
            event = OrchestrationEvent(
                step="LIFECYCLE_TRANSITION",
                status="SUCCESS" if len(results["errors"]) == 0 else "PARTIAL",
                message=(
                    f"{'[DRY RUN] ' if dry_run else ''}"
                    f"전환 체크 완료: STEP1→2 {results['step1_to_step2']['transitioned']}건, "
                    f"STEP2→3 {results['step2_to_step3']['transitioned']}건"
                ),
                details={
                    "dry_run": dry_run,
                    "step1_to_step2": {
                        "checked": results["step1_to_step2"]["checked"],
                        "transitioned": results["step1_to_step2"]["transitioned"]
                    },
                    "step2_to_step3": {
                        "checked": results["step2_to_step3"]["checked"],
                        "transitioned": results["step2_to_step3"]["transitioned"]
                    },
                    "total_transitioned": results["total_transitioned"],
                    "execution_time_seconds": results["execution_time_seconds"],
                    "errors": results["errors"]
                }
            )
            session.add(event)
            session.commit()
        except Exception as e:
            logger.error(f"오케스트레이션 이벤트 기록 실패: {e}", exc_info=True)

    async def run_once(self, dry_run: bool = True):
        """
        단일 실행 (테스트 또는 수동 트리거용)
        
        Args:
            dry_run: True면 전환 조건만 체크, False면 실제 전환 수행
        """
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}단일 실행 모드로 라이프사이클 전환 체크 시작")
        
        results = await self.check_and_transition_all(dry_run=dry_run)
        
        # 요약 로그
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}실행 결과 요약:")
        logger.info(f"  STEP 1 → 2: {results['step1_to_step2']['checked']}건 체크, "
                   f"{results['step1_to_step2']['transitioned']}건 전환")
        logger.info(f"  STEP 2 → 3: {results['step2_to_step3']['checked']}건 체크, "
                   f"{results['step2_to_step3']['transitioned']}건 전환")
        logger.info(f"  총 전환: {results['total_transitioned']}건")
        logger.info(f"  실행 시간: {results['execution_time_seconds']}초")
        
        if results["errors"]:
            logger.warning(f"  오류: {len(results['errors'])}건")
            for error in results["errors"]:
                logger.warning(f"    - {error}")
        
        return results


# 싱글톤 인스턴스
_lifecycle_scheduler: Optional[LifecycleScheduler] = None


def get_lifecycle_scheduler() -> LifecycleScheduler:
    """라이프사이클 스케줄러 인스턴스 가져오기"""
    global _lifecycle_scheduler
    if _lifecycle_scheduler is None:
        _lifecycle_scheduler = LifecycleScheduler()
    return _lifecycle_scheduler
