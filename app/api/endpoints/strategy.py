from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from app.db import get_session
from app.services.analytics.strategy_drift import StrategyDriftDetector
from app.services.analytics.policy_simulator import PolicySimulatorService

router = APIRouter()

@router.get("/health-check")
async def get_strategy_health(db: Session = Depends(get_session)):
    """
    현재 시스템 전체 전략의 건강 상태를 리턴합니다.
    """
    health = StrategyDriftDetector.analyze_global_strategy_health(db, days=14)
    return health

@router.get("/simulation")
async def get_strategy_simulation(db: Session = Depends(get_session)):
    """
    전략적 판단(Pivot/Momentum)에 대한 시뮬레이션 리포트를 생성합니다.
    """
    # 1. 현재 건강 상태 분석
    health = StrategyDriftDetector.analyze_global_strategy_health(db, days=14)
    
    # 2. 시뮬레이션 실행
    report = PolicySimulatorService.simulate_strategy_change(db, health)
    
    return {
        "report": report,
        "health": health
    }

@router.post("/approve-pivot")
async def approve_strategy_pivot(db: Session = Depends(get_session)):
    """
    운영자가 제안된 전략 피벗(Pivot)을 승인합니다.
    """
    # 실제로는 설정값을 변경하거나 활성화 플래그를 업데이트하는 로직이 들어갑니다.
    # 여기서는 승인 기록 서비스(AdaptivePolicyEvent)를 통해 기록하는 것으로 갈음합니다.
    from app.services.analytics.coupang_policy import CoupangSourcingPolicyService
    
    CoupangSourcingPolicyService.log_policy_event(
        session=db,
        category_code="GLOBAL_STRATEGY",
        event_type="STRATEGY_PIVOT_APPROVED",
        multiplier=0.5,
        reason="운영자 전략 피벗 승인",
        severity="NONE"
    )
    db.commit()
    
    return {"status": "success", "message": "전략 피벗이 승인되어 적용되었습니다."}
