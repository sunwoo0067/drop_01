from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import SystemSetting, AutonomyPolicy

class GovernanceManager:
    """
    전역 킬스위치 및 특정 세그먼트의 동결(Freeze) 등 자율성 시스템의 운영 통제를 담당합니다.
    """
    
    def __init__(self, db: Session):
        self.db = db

    def set_global_kill_switch(self, enabled: bool):
        """
        비상 상황 시 모든 자동 집행을 즉시 중단시키거나 재개합니다.
        """
        stmt = select(SystemSetting).where(SystemSetting.key == "AUTONOMY_KILL_SWITCH")
        setting = self.db.execute(stmt).scalars().first()
        
        if not setting:
            setting = SystemSetting(key="AUTONOMY_KILL_SWITCH", value={"enabled": enabled})
            self.db.add(setting)
        else:
            # SQLAlchemy JSONB mutation 주의: 필드 재할당 필요
            val = dict(setting.value)
            val["enabled"] = enabled
            setting.value = val
            
        self.db.commit()

    def freeze_segment(self, segment_key: str):
        """
        특정 카테고리나 전략군에서 이상 징후 발견 시 해당 세그먼트만 즉시 수동 모드로 전환합니다.
        """
        stmt = select(AutonomyPolicy).where(AutonomyPolicy.segment_key == segment_key)
        policy = self.db.execute(stmt).scalars().first()
        
        if policy:
            policy.status = "FROZEN"
            policy.tier = 0 # 즉시 Manual 단계로 강등
            self.db.commit()
            return True
        return False

    def unfreeze_segment(self, segment_key: str, initial_tier: int = 1):
        """
        동결된 세그먼트를 해제하고 하위 티어부터 복구합니다.
        """
        stmt = select(AutonomyPolicy).where(AutonomyPolicy.segment_key == segment_key)
        policy = self.db.execute(stmt).scalars().first()
        
        if policy:
            policy.status = "ACTIVE"
            policy.tier = initial_tier
            self.db.commit()
            return True
        return False
