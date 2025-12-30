import logging
from typing import Tuple, Optional
from sqlalchemy.orm import Session
from app.services.analytics.reporting import CoupangOperationalReportService
from app.settings import settings

logger = logging.getLogger(__name__)

class CoupangGuardrailService:
    """
    시스템 이상 징후를 감지하고 안전 장치를 작동시킵니다.
    """
    
    @staticmethod
    def check_system_integrity(session: Session) -> Tuple[bool, str, Optional[str]]:
        """
        시스템 상태를 체크하고 안정 모드 전환이 필요한지 판단합니다.
        Returns: (is_critical, reason, recommended_mode)
        """
        # 최근 2일간의 지표 비교
        stats = CoupangOperationalReportService.get_daily_operational_stats(session, days=2)
        time_series = stats.get("time_series", [])
        
        if len(time_series) < 2:
            return False, "데이터 부족으로 가드레일 스킵", None
            
        today = time_series[0]
        yesterday = time_series[1]
        
        # 1. 성공률 급락 감지
        sr_diff = yesterday["success_rate"] - today["success_rate"]
        threshold = settings.coupang_stability_declination_threshold * 100 # %p 단위 비교
        
        if sr_diff >= threshold and today["attempted"] >= 10: # 최소 10건 이상일 때만 작동
            msg = f"성공률 급락 감지: 전일({yesterday['success_rate']}%) -> 금일({today['success_rate']}%). 차이: {sr_diff:.1f}%p"
            logger.warning(f"⚠️ [GUARDRAIL] {msg}")
            return True, msg, "enforce_lite"
            
        # 2. BLOCK 등급 급증 감지
        # 전체 소싱 시도 중 BLOCK 비중 계산
        today_total = sum(stats["grade_distribution"].values())
        if today_total > 0:
            block_ratio = today["block_count"] / today_total
            # 과거 평균과 비교하는 로직이 좋으나, 일단 설정값 기반으로 단순 체크
            # 여기서는 어제와 오늘을 비교
            yesterday_total = yesterday.get("attempted_sourcing", today_total) # 임시
            yesterday_block_ratio = yesterday["block_count"] / yesterday_total if yesterday_total > 0 else 0
            
            surge_threshold = settings.coupang_block_surge_threshold
            if yesterday_block_ratio > 0 and (block_ratio / yesterday_block_ratio) >= surge_threshold:
                msg = f"BLOCK 등급 급증 감지: 전일({yesterday_block_ratio*100:.1f}%) -> 금일({block_ratio*100:.1f}%)"
                logger.warning(f"⚠️ [GUARDRAIL] {msg}")
                return True, msg, "shadow"

        return False, "정상 운영 중", None

    @staticmethod
    def apply_automatic_downgrade(session: Session):
        """
        필요 시 설정을 자동으로 하향 조정합니다. (In-memory)
        실제 환경에서는 DB 세팅 테이블이나 Redis 등을 업데이트해야 함.
        """
        is_critical, reason, recommended_mode = CoupangGuardrailService.check_system_integrity(session)
        
        if is_critical and recommended_mode:
            logger.error(f"🚨 [AUTOMATIC DOWNGRADE] {reason} -> 추천 모드: {recommended_mode}")
            # settings.coupang_sourcing_policy_mode = recommended_mode
            # settings.coupang_stability_mode = True
            # TODO: 외부 저장소(DB)에 설정값을 저장하는 로직 추가 필요
            return True, reason, recommended_mode
            
        return False, reason, None
