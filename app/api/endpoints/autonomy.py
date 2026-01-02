"""
자율성 거버넌스 API 엔드포인트

자율성 정책, 의사결정 로그, 킬스위치를 관리합니다.
"""
import uuid
from datetime import datetime
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import AutonomyPolicy, AutonomyDecisionLog, SystemSetting, PricingRecommendation

router = APIRouter()


def _to_iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.isoformat()


class AutonomyPolicyOut(BaseModel):
    id: str
    segment_key: str
    vendor: Optional[str]
    channel: Optional[str]
    category_code: Optional[str]
    strategy_id: Optional[str]
    lifecycle_stage: Optional[str]
    tier: int
    status: str
    config_override: Optional[dict]
    created_at: str
    updated_at: str


class AutonomyPolicyUpdateIn(BaseModel):
    tier: int
    status: str = "ACTIVE"
    config_override: Optional[dict] = None


class AutonomyDecisionLogOut(BaseModel):
    id: str
    recommendation_id: str
    segment_key: str
    tier_used: int
    decision: str
    confidence: Optional[float]
    expected_margin: Optional[float]
    reasons: list[str]
    created_at: str


class SegmentStatsOut(BaseModel):
    segment_key: str
    tier: int
    total_decisions: int
    applied_count: int
    success_rate: float
    avg_confidence: float


class KillSwitchOut(BaseModel):
    enabled: bool
    last_updated: Optional[str]


class KillSwitchIn(BaseModel):
    enabled: bool


@router.get("/policies", response_model=list[AutonomyPolicyOut])
def list_autonomy_policies(
    status: Optional[str] = Query(None, description="ACTIVE, FROZEN 필터"),
    tier: Optional[int] = Query(None, description="Tier 필터"),
    limit: int = Query(100, description="최대 반환 건수"),
    session: Session = Depends(get_session)
) -> list[AutonomyPolicyOut]:
    """
    자율성 정책 목록을 조회합니다.
    """
    stmt = select(AutonomyPolicy).order_by(AutonomyPolicy.updated_at.desc())
    
    if status:
        stmt = stmt.where(AutonomyPolicy.status == status)
    if tier is not None:
        stmt = stmt.where(AutonomyPolicy.tier == tier)
    
    stmt = stmt.limit(limit)
    policies = session.scalars(stmt).all()
    
    return [
        AutonomyPolicyOut(
            id=str(p.id),
            segment_key=p.segment_key,
            vendor=p.vendor,
            channel=p.channel,
            category_code=p.category_code,
            strategy_id=str(p.strategy_id) if p.strategy_id else None,
            lifecycle_stage=p.lifecycle_stage,
            tier=p.tier,
            status=p.status,
            config_override=p.config_override,
            created_at=_to_iso(p.created_at),
            updated_at=_to_iso(p.updated_at),
        )
        for p in policies
    ]


@router.get("/policies/{policy_id}", response_model=AutonomyPolicyOut)
def get_autonomy_policy(
    policy_id: uuid.UUID,
    session: Session = Depends(get_session)
) -> AutonomyPolicyOut:
    """
    특정 자율성 정책을 조회합니다.
    """
    policy = session.get(AutonomyPolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="자율성 정책을 찾을 수 없습니다")
    
    return AutonomyPolicyOut(
        id=str(policy.id),
        segment_key=policy.segment_key,
        vendor=policy.vendor,
        channel=policy.channel,
        category_code=policy.category_code,
        strategy_id=str(policy.strategy_id) if policy.strategy_id else None,
        lifecycle_stage=policy.lifecycle_stage,
        tier=policy.tier,
        status=policy.status,
        config_override=policy.config_override,
        created_at=_to_iso(policy.created_at),
        updated_at=_to_iso(policy.updated_at),
    )


@router.patch("/policies/{policy_id}", response_model=AutonomyPolicyOut)
def update_autonomy_policy(
    policy_id: uuid.UUID,
    payload: AutonomyPolicyUpdateIn,
    session: Session = Depends(get_session)
) -> AutonomyPolicyOut:
    """
    자율성 정책을 업데이트합니다.
    """
    policy = session.get(AutonomyPolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="자율성 정책을 찾을 수 없습니다")
    
    # 티어 범위 검증 (0-3)
    if payload.tier not in [0, 1, 2, 3]:
        raise HTTPException(status_code=400, detail="Tier는 0-3 사이어야 합니다")
    
    # 상태 검증
    if payload.status not in ["ACTIVE", "FROZEN"]:
        raise HTTPException(status_code=400, detail="상태는 ACTIVE 또는 FROZEN여야 합니다")
    
    policy.tier = payload.tier
    policy.status = payload.status
    if payload.config_override is not None:
        policy.config_override = payload.config_override
    
    session.commit()
    
    return AutonomyPolicyOut(
        id=str(policy.id),
        segment_key=policy.segment_key,
        vendor=policy.vendor,
        channel=policy.channel,
        category_code=policy.category_code,
        strategy_id=str(policy.strategy_id) if policy.strategy_id else None,
        lifecycle_stage=policy.lifecycle_stage,
        tier=policy.tier,
        status=policy.status,
        config_override=policy.config_override,
        created_at=_to_iso(policy.created_at),
        updated_at=_to_iso(policy.updated_at),
    )


@router.post("/policies", response_model=AutonomyPolicyOut, status_code=201)
def create_autonomy_policy(
    vendor: str = Query(..., description="공급처 (예: ownerclan)"),
    channel: str = Query(..., description="채널 (예: COUPANG)"),
    category_code: Optional[str] = Query(None, description="카테고리 코드"),
    strategy_id: Optional[str] = Query(None, description="가격 전략 ID"),
    lifecycle_stage: str = Query("STEP_1", description="라이프사이클 단계"),
    tier: int = Query(0, description="자율 등급 (0-3)"),
    session: Session = Depends(get_session)
) -> AutonomyPolicyOut:
    """
    새로운 자율성 정책을 생성합니다.
    """
    from app.services.pricing.segment_resolver import SegmentResolver
    
    resolver = SegmentResolver()
    segment_metadata = resolver.resolve_segment_metadata(
        vendor=vendor,
        channel=channel,
        category_code=category_code,
        strategy_id=uuid.UUID(strategy_id) if strategy_id else None,
        lifecycle_stage=lifecycle_stage
    )
    segment_key = resolver.get_segment_key(segment_metadata)
    
    # 이미 존재하는 정책 확인
    existing = session.execute(
        select(AutonomyPolicy).where(AutonomyPolicy.segment_key == segment_key)
    ).scalars().first()
    
    if existing:
        raise HTTPException(status_code=400, detail=f"이미 존재하는 세그먼트 정책입니다: {segment_key}")
    
    # 티어 범위 검증
    if tier not in [0, 1, 2, 3]:
        raise HTTPException(status_code=400, detail="Tier는 0-3 사이어야 합니다")
    
    policy = AutonomyPolicy(
        segment_key=segment_key,
        vendor=vendor,
        channel=channel,
        category_code=category_code,
        strategy_id=uuid.UUID(strategy_id) if strategy_id else None,
        lifecycle_stage=lifecycle_stage,
        tier=tier,
        status="ACTIVE",
    )
    
    session.add(policy)
    session.commit()
    
    return AutonomyPolicyOut(
        id=str(policy.id),
        segment_key=policy.segment_key,
        vendor=policy.vendor,
        channel=policy.channel,
        category_code=policy.category_code,
        strategy_id=str(policy.strategy_id) if policy.strategy_id else None,
        lifecycle_stage=policy.lifecycle_stage,
        tier=policy.tier,
        status=policy.status,
        config_override=policy.config_override,
        created_at=_to_iso(policy.created_at),
        updated_at=_to_iso(policy.updated_at),
    )


@router.get("/decision-logs", response_model=list[AutonomyDecisionLogOut])
def list_autonomy_decision_logs(
    decision: Optional[str] = Query(None, description="APPLIED, PENDING, REJECTED 필터"),
    segment_key: Optional[str] = Query(None, description="세그먼트 키 필터 (부분 일치)"),
    tier: Optional[int] = Query(None, description="Tier 필터"),
    limit: int = Query(100, description="최대 반환 건수"),
    session: Session = Depends(get_session)
) -> list[AutonomyDecisionLogOut]:
    """
    자율적 의사결정 로그를 조회합니다.
    """
    stmt = select(AutonomyDecisionLog).order_by(AutonomyDecisionLog.created_at.desc())
    
    if decision:
        stmt = stmt.where(AutonomyDecisionLog.decision == decision)
    if segment_key:
        stmt = stmt.where(AutonomyDecisionLog.segment_key.contains(segment_key))
    if tier is not None:
        stmt = stmt.where(AutonomyDecisionLog.tier_used == tier)
    
    stmt = stmt.limit(limit)
    logs = session.scalars(stmt).all()
    
    return [
        AutonomyDecisionLogOut(
            id=str(log.id),
            recommendation_id=str(log.recommendation_id),
            segment_key=log.segment_key,
            tier_used=log.tier_used,
            decision=log.decision,
            confidence=log.confidence,
            expected_margin=log.expected_margin,
            reasons=log.reasons or [],
            created_at=_to_iso(log.created_at),
        )
        for log in logs
    ]


@router.get("/segment-stats", response_model=list[SegmentStatsOut])
def get_segment_stats(
    days: int = Query(7, description="통계 기간 (일)"),
    session: Session = Depends(get_session)
) -> list[SegmentStatsOut]:
    """
    세그먼트별 의사결정 성과 통계를 조회합니다.
    """
    from datetime import timedelta, timezone
    
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    # 세그먼트별 통계 집계
    stmt = (
        select(
            AutonomyDecisionLog.segment_key,
            AutonomyDecisionLog.tier_used.label("tier"),
            func.count(AutonomyDecisionLog.id).label("total_decisions"),
            func.sum(
                func.cast(AutonomyDecisionLog.decision == "APPLIED", func.int)
            ).label("applied_count"),
            func.avg(AutonomyDecisionLog.confidence).label("avg_confidence")
        )
        .where(AutonomyDecisionLog.created_at >= since)
        .group_by(AutonomyDecisionLog.segment_key, AutonomyDecisionLog.tier_used)
        .order_by(AutonomyDecisionLog.segment_key)
    )
    
    results = session.execute(stmt).all()
    
    stats = []
    for row in results:
        total = row.total_decisions
        applied = row.applied_count or 0
        success_rate = (applied / total) if total > 0 else 0.0
        avg_conf = row.avg_confidence or 0.0
        
        stats.append(
            SegmentStatsOut(
                segment_key=row.segment_key,
                tier=row.tier,
                total_decisions=total,
                applied_count=applied,
                success_rate=round(success_rate, 4),
                avg_confidence=round(avg_conf, 4),
            )
        )
    
    return stats


@router.get("/kill-switch/processing", response_model=KillSwitchOut)
def get_processing_kill_switch(
    session: Session = Depends(get_session)
) -> KillSwitchOut:
    """
    상품 가공 전역 킬스위치 상태를 조회합니다.
    """
    setting = session.execute(
        select(SystemSetting).where(SystemSetting.key == "PROCESSING_AUTONOMY_KILL_SWITCH")
    ).scalars().first()
    
    enabled = bool(setting and setting.value.get("enabled"))
    
    return KillSwitchOut(
        enabled=enabled,
        last_updated=_to_iso(setting.updated_at) if setting else None,
    )


@router.post("/kill-switch/processing", response_model=KillSwitchOut)
def set_processing_kill_switch(
    payload: KillSwitchIn,
    session: Session = Depends(get_session)
) -> KillSwitchOut:
    """
    상품 가공 전역 킬스위치를 설정합니다.
    """
    setting = session.execute(
        select(SystemSetting).where(SystemSetting.key == "PROCESSING_AUTONOMY_KILL_SWITCH")
    ).scalars().first()
    
    if setting:
        setting.value = {"enabled": payload.enabled}
    else:
        setting = SystemSetting(
            key="PROCESSING_AUTONOMY_KILL_SWITCH",
            value={"enabled": payload.enabled},
            description="상품 가공 자율성 전역 킬스위치",
        )
        session.add(setting)
    
    session.commit()
    
    return KillSwitchOut(
        enabled=payload.enabled,
        last_updated=_to_iso(setting.updated_at),
    )


@router.get("/kill-switch/pricing", response_model=KillSwitchOut)
def get_pricing_kill_switch(
    session: Session = Depends(get_session)
) -> KillSwitchOut:
    """
    가격 변경 전역 킬스위치 상태를 조회합니다.
    """
    setting = session.execute(
        select(SystemSetting).where(SystemSetting.key == "AUTONOMY_KILL_SWITCH")
    ).scalars().first()
    
    enabled = bool(setting and setting.value.get("enabled"))
    
    return KillSwitchOut(
        enabled=enabled,
        last_updated=_to_iso(setting.updated_at) if setting else None,
    )


@router.post("/kill-switch/pricing", response_model=KillSwitchOut)
def set_pricing_kill_switch(
    payload: KillSwitchIn,
    session: Session = Depends(get_session)
) -> KillSwitchOut:
    """
    가격 변경 전역 킬스위치를 설정합니다.
    """
    setting = session.execute(
        select(SystemSetting).where(SystemSetting.key == "AUTONOMY_KILL_SWITCH")
    ).scalars().first()
    
    if setting:
        setting.value = {"enabled": payload.enabled}
    else:
        setting = SystemSetting(
            key="AUTONOMY_KILL_SWITCH",
            value={"enabled": payload.enabled},
            description="가격 변경 자율성 전역 킬스위치",
        )
        session.add(setting)
    
    session.commit()
    
    return KillSwitchOut(
        enabled=payload.enabled,
        last_updated=_to_iso(setting.updated_at),
    )


@router.post("/tuner/run", status_code=200)
def run_autonomy_tuner(
    days: int = Query(14, description="분석 기간 (일)"),
    session: Session = Depends(get_session)
) -> dict:
    """
    자율 정책 튜너를 실행합니다.
    세그먼트별 성과를 분석하여 승격/강등을 제안하거나 집행합니다.
    """
    from app.services.pricing.autonomy_tuner import AutonomyTuner
    
    tuner = AutonomyTuner(session)
    results = tuner.run_evolution_cycle(days=days)
    
    return {
        "analyzed_segments": len(results),
        "results": results,
        "message": f"{len(results)}개 세그먼트 분석 완료"
    }
