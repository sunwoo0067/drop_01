from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, ConfigDict
import uuid
from app.services.analytics.kpi_engine import KPIEngine

from app.db import get_session
from app.models import SyncRun, SyncRunError, ProfitSnapshot, Product, PricingRecommendation, PricingSettings, MarketAccount, PriceChangeLog, PricingExperiment, ProductExperimentMapping
from app.services.pricing.enforcer import PriceEnforcer

router = APIRouter()

class SyncRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vendor: str
    channel: str
    status: str
    read_count: int
    write_count: int
    error_count: int
    duration_ms: Optional[int]
    started_at: datetime
    finished_at: Optional[datetime]

class SyncChannelMetric(BaseModel):
    vendor: str
    channel: str
    last_status: str
    last_run_at: Optional[datetime]
    success_rate: float
    avg_duration_ms: float
    total_errors_24h: int

class SyncMetricsResponse(BaseModel):
    summary: List[SyncChannelMetric]
    recent_runs: List[SyncRunResponse]

class ProfitAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    product_name: Optional[str] = None
    channel: str
    current_price: int
    estimated_profit: int
    margin_rate: float
    reason_codes: Optional[List[str]] = None
    created_at: datetime

class MarginTrendItem(BaseModel):
    date: str
    avg_margin: float
    total_profit: int
    order_count: int

class SimulationResponse(BaseModel):
    pending_reco_count: int
    current_base_profit: int
    simulated_profit: int
    expected_lift: int
    lift_percentage: float

class PricingRecommendationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    product_name: Optional[str] = None
    market_account_id: uuid.UUID
    current_price: int
    recommended_price: int
    expected_margin: Optional[float] = None
    confidence: float
    reasons: Optional[List[str]] = None
    status: str
    created_at: datetime

class PricingSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    market_account_id: uuid.UUID
    auto_mode: str
    confidence_threshold: float
    max_changes_per_hour: int
    cooldown_hours: int

class PricingSettingsUpdate(BaseModel):
    auto_mode: Optional[str] = None
    confidence_threshold: Optional[float] = None
    max_changes_per_hour: Optional[int] = None
    cooldown_hours: Optional[int] = None

class AutomationStatsResponse(BaseModel):
    total_recommendations: int
    pending_count: int
    applied_24h: int
    throttle_status: dict # account_id -> current_usage / limit

class PricingExperimentCreate(BaseModel):
    name: str
    test_ratio: float = 0.1
    config_variant: Optional[dict] = None

class PricingExperimentUpdate(BaseModel):
    status: Optional[str] = None
    metrics_summary: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class PricingExperimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str
    test_ratio: float
    config_variant: Optional[dict] = None
    metrics_summary: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class TuningRecommendationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    strategy_id: uuid.UUID
    suggested_config: dict
    reason_code: str
    reason_detail: Optional[str] = None
    status: str
    created_at: datetime
    applied_at: Optional[datetime] = None

@router.get("/sync-metrics", response_model=SyncMetricsResponse)
def get_sync_metrics(
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session)
):
    """동기화 채널별 메트릭 및 최근 실행 이력 조회"""
    
    # 1. 최근 실행 이력
    recent_runs = session.query(SyncRun).order_by(desc(SyncRun.started_at)).limit(limit).all()
    
    # 2. 채널별 메트릭 계산 (최근 24시간 기준)
    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    
    # 각 벤더/채널별 최신 실행 정보
    subquery = session.query(
        SyncRun.vendor,
        SyncRun.channel,
        func.max(SyncRun.started_at).label("max_started_at")
    ).group_by(SyncRun.vendor, SyncRun.channel).subquery()
    
    latest_runs = session.query(SyncRun).join(
        subquery,
        (SyncRun.vendor == subquery.c.vendor) & 
        (SyncRun.channel == subquery.c.channel) & 
        (SyncRun.started_at == subquery.c.max_started_at)
    ).all()
    
    # 24시간 통계
    stats_24h = session.query(
        SyncRun.vendor,
        SyncRun.channel,
        func.count(SyncRun.id).label("total_count"),
        func.sum(SyncRun.error_count).label("total_errors"),
        func.avg(SyncRun.duration_ms).label("avg_duration"),
        func.count(SyncRun.id).filter(SyncRun.status == "success").label("success_count")
    ).filter(SyncRun.started_at >= since_24h).group_by(SyncRun.vendor, SyncRun.channel).all()
    
    stats_map = {(s.vendor, s.channel): s for s in stats_24h}
    
    summary = []
    for latest in latest_runs:
        stat = stats_map.get((latest.vendor, latest.channel))
        
        success_rate = 0.0
        avg_dur = 0.0
        err_24h = 0
        
        if stat and stat.total_count > 0:
            success_rate = (stat.success_count / stat.total_count) * 100
            avg_dur = float(stat.avg_duration or 0)
            err_24h = int(stat.total_errors or 0)
            
        summary.append(SyncChannelMetric(
            vendor=latest.vendor,
            channel=latest.channel,
            last_status=latest.status,
            last_run_at=latest.started_at,
            success_rate=round(success_rate, 2),
            avg_duration_ms=round(avg_dur, 2),
            total_errors_24h=err_24h
        ))
        
    return SyncMetricsResponse(
        summary=summary,
        recent_runs=[SyncRunResponse.model_validate(r) for r in recent_runs]
    )

@router.get("/sync-runs/{run_id}/errors", response_model=List[dict])
def get_sync_run_errors(
    run_id: str,
    session: Session = Depends(get_session)
):
    """특정 실행의 에러 상세 로그 조회"""
    errors = session.query(SyncRunError).filter_by(run_id=run_id).all()
    return [
        {
            "id": str(e.id),
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "message": e.message,
            "stack": e.stack,
            "created_at": e.created_at
        } for e in errors
    ]

@router.get("/profit-alerts", response_model=List[ProfitAlertResponse])
def get_profit_alerts(
    limit: int = Query(50, ge=1, le=200),
    is_risk: bool = True,
    session: Session = Depends(get_session)
):
    """수익성 위험 알림 리스트 조회"""
    alerts = session.query(
        ProfitSnapshot,
        Product.name.label("product_name")
    ).join(Product, ProfitSnapshot.product_id == Product.id)\
     .filter(ProfitSnapshot.is_risk == is_risk)\
     .order_by(desc(ProfitSnapshot.created_at))\
     .limit(limit).all()
    
    result = []
    for row in alerts:
        snapshot, prod_name = row
        resp = ProfitAlertResponse.model_validate(snapshot)
        resp.product_name = prod_name
        result.append(resp)
        
    return result

@router.get("/analytics/margin-trend", response_model=List[MarginTrendItem])
def get_margin_trend(
    days: int = Query(30, ge=1, le=365),
    session: Session = Depends(get_session)
):
    """일자별 마진율 및 수익 추이 조회"""
    engine = KPIEngine(session)
    return engine.get_margin_trend(days=days)

@router.get("/analytics/simulation", response_model=SimulationResponse)
def get_profit_simulation(
    session: Session = Depends(get_session)
):
    """가격 권고 적용 시 예상 수익 시뮬레이션 조회"""
    engine = KPIEngine(session)
    return engine.get_what_if_simulation()

@router.get("/pricing/recommendations", response_model=List[PricingRecommendationResponse])
def get_pricing_recommendations(
    status: str = "PENDING",
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session)
):
    """가격 권고 리스트 조회"""
    recs = session.query(
        PricingRecommendation,
        Product.name.label("product_name")
    ).outerjoin(Product, PricingRecommendation.product_id == Product.id)\
     .filter(PricingRecommendation.status == status)\
     .order_by(desc(PricingRecommendation.created_at))\
     .limit(limit).all()
    
    result = []
    for row in recs:
        rec, prod_name = row
        resp = PricingRecommendationResponse.model_validate(rec)
        resp.product_name = prod_name
        result.append(resp)
    return result

@router.post("/pricing/recommendations/{reco_id}/apply")
async def apply_pricing_recommendation(
    reco_id: str,
    session: Session = Depends(get_session)
):
    """특정 가격 권고를 수동으로 승인하여 마켓에 반영"""
    rec = session.query(PricingRecommendation).filter_by(id=reco_id).first()
    if not rec:
        return {"success": False, "message": "Recommendation not found"}
    
    if rec.status != "PENDING":
        return {"success": False, "message": f"Invalid status: {rec.status}"}
    
    enforcer = PriceEnforcer(session)
    await enforcer.enforce(rec, mode="ENFORCE")
    
    return {"success": True, "message": f"Successfully applied price change for product {rec.product_id}"}

@router.get("/pricing/settings/{account_id}", response_model=PricingSettingsResponse)
def get_pricing_settings(
    account_id: uuid.UUID,
    session: Session = Depends(get_session)
):
    """마켓 계정별 자동화 정책 설정 조회"""
    settings = session.query(PricingSettings).filter_by(market_account_id=account_id).first()
    if not settings:
        # Default settings if none exist
        return PricingSettingsResponse(
            market_account_id=account_id,
            auto_mode="SHADOW",
            confidence_threshold=0.95,
            max_changes_per_hour=50,
            cooldown_hours=24
        )
    return settings

@router.patch("/pricing/settings/{account_id}", response_model=PricingSettingsResponse)
def update_pricing_settings(
    account_id: uuid.UUID,
    updates: PricingSettingsUpdate,
    session: Session = Depends(get_session)
):
    """마켓 계정별 자동화 정책 설정 업데이트"""
    settings = session.query(PricingSettings).filter_by(market_account_id=account_id).first()
    if not settings:
        settings = PricingSettings(market_account_id=account_id)
        session.add(settings)
    
    if updates.auto_mode is not None: settings.auto_mode = updates.auto_mode
    if updates.confidence_threshold is not None: settings.confidence_threshold = updates.confidence_threshold
    if updates.max_changes_per_hour is not None: settings.max_changes_per_hour = updates.max_changes_per_hour
    if updates.cooldown_hours is not None: settings.cooldown_hours = updates.cooldown_hours
    
    session.commit()
    session.refresh(settings)
    return settings

@router.get("/pricing/stats", response_model=AutomationStatsResponse)
def get_pricing_stats(session: Session = Depends(get_session)):
    """전체 가격 자동화 가동 현황 및 스로틀링 통계 조회"""
    now = datetime.now(timezone.utc)
    one_day_ago = now - timedelta(days=1)
    one_hour_ago = now - timedelta(hours=1)
    
    total_recs = session.query(func.count(PricingRecommendation.id)).scalar()
    pending = session.query(func.count(PricingRecommendation.id)).filter_by(status="PENDING").scalar()
    
    applied_24h = session.query(func.count(PriceChangeLog.id)).filter(
        PriceChangeLog.status == "SUCCESS",
        PriceChangeLog.created_at >= one_day_ago
    ).scalar()
    
    # Throttle status per account
    accounts = session.query(MarketAccount).filter_by(is_active=True).all()
    throttle_status = {}
    for acc in accounts:
        settings = session.query(PricingSettings).filter_by(market_account_id=acc.id).first()
        limit = settings.max_changes_per_hour if settings else 50
        usage = session.query(func.count(PriceChangeLog.id)).filter(
            PriceChangeLog.market_account_id == acc.id,
            PriceChangeLog.status == "SUCCESS",
            PriceChangeLog.created_at >= one_hour_ago
        ).scalar()
        throttle_status[str(acc.id)] = {"usage": usage, "limit": limit, "name": acc.name}
        
    return AutomationStatsResponse(
        total_recommendations=total_recs,
        pending_count=pending,
        applied_24h=applied_24h,
        throttle_status=throttle_status
    )
@router.post("/pricing/experiments", response_model=PricingExperimentResponse)
def create_pricing_experiment(
    data: PricingExperimentCreate,
    session: Session = Depends(get_session)
):
    """새로운 가격 정책 실험 생성"""
    exp = PricingExperiment(
        name=data.name,
        test_ratio=data.test_ratio,
        config_variant=data.config_variant
    )
    session.add(exp)
    session.commit()
    session.refresh(exp)
    return exp

@router.get("/pricing/experiments", response_model=List[PricingExperimentResponse])
def list_pricing_experiments(
    status: Optional[str] = None,
    session: Session = Depends(get_session)
):
    """가격 정책 실험 목록 조회"""
    query = session.query(PricingExperiment)
    if status:
        query = query.filter_by(status=status)
    return query.order_by(desc(PricingExperiment.created_at)).all()

@router.patch("/pricing/experiments/{exp_id}", response_model=PricingExperimentResponse)
def update_pricing_experiment(
    exp_id: uuid.UUID,
    updates: PricingExperimentUpdate,
    session: Session = Depends(get_session)
):
    """실행 중인 실험 상태 및 결과 요약 업데이트"""
    exp = session.query(PricingExperiment).filter_by(id=exp_id).first()
    if not exp:
        return {"error": "Experiment not found"}
    
    if updates.status is not None: exp.status = updates.status
    if updates.metrics_summary is not None: exp.metrics_summary = updates.metrics_summary
    
    session.commit()
    session.refresh(exp)
    return exp

@router.post("/pricing/experiments/{exp_id}/optimize")
async def optimize_from_experiment(
    exp_id: uuid.UUID,
    session: Session = Depends(get_session)
):
    """실행 중인 실험을 분석하고 우수한 정책을 전역에 적용"""
    from app.services.pricing.optimizer import LearningLoop
    optimizer = LearningLoop(session)
    result = optimizer.finalize_and_optimize(exp_id)
    return result


@router.get("/pricing/strategies/stats", response_model=List[dict])
def get_strategy_stats(
    days: int = Query(7, ge=1, le=30),
    session: Session = Depends(get_session)
):
    """전략별 성과 지표 조회"""
    from app.services.pricing.strategy_monitor import StrategyMonitor
    monitor = StrategyMonitor(session)
    return monitor.get_strategy_metrics(days=days)


@router.get("/pricing/strategies/tuning-recommendations", response_model=List[TuningRecommendationResponse])
def list_tuning_recommendations(
    status: str = "PENDING",
    session: Session = Depends(get_session)
):
    """전략 파라미터 조정 권고 목록 조회"""
    from app.models import TuningRecommendation
    return session.query(TuningRecommendation).filter_by(status=status).order_by(desc(TuningRecommendation.created_at)).all()


@router.post("/pricing/strategies/tuning-recommendations/trigger")
def trigger_tuning_cycle(
    session: Session = Depends(get_session)
):
    """데이터 기반의 전략 튜닝 주기를 강제로 실행"""
    from app.services.pricing.strategy_tuner import StrategyTuner
    tuner = StrategyTuner(session)
    new_recs = tuner.run_tuning_cycle()
    return {"success": True, "new_recommendations_count": len(new_recs)}


@router.post("/pricing/strategies/tuning-recommendations/{reco_id}/apply")
def apply_tuning_recommendation(
    reco_id: str,
    session: Session = Depends(get_session)
):
    """관리자가 승인한 권고안을 실제 전략 파라미터에 반영"""
    from app.services.pricing.strategy_tuner import StrategyTuner
    tuner = StrategyTuner(session)
    success = tuner.apply_recommendation(reco_id)
    return {"success": success}


# PR-15: Progressive Autonomy Endpoints

@router.post("/pricing/autonomy/kill-switch")
def set_kill_switch(
    enabled: bool,
    session: Session = Depends(get_session)
):
    """자율 집행 전역 킬스위치 설정"""
    from app.services.pricing.governance_manager import GovernanceManager
    mgr = GovernanceManager(session)
    mgr.set_global_kill_switch(enabled)
    return {"success": True, "kill_switch_enabled": enabled}


@router.get("/pricing/autonomy/policies", response_model=List[dict])
def list_autonomy_policies(
    session: Session = Depends(get_session)
):
    """세그먼트별 자율 집행 정책 목록 조회"""
    from app.models import AutonomyPolicy
    policies = session.query(AutonomyPolicy).all()
    return [
        {
            "id": p.id,
            "segment_key": p.segment_key,
            "vendor": p.vendor,
            "channel": p.channel,
            "category_code": p.category_code,
            "tier": p.tier,
            "status": p.status,
            "updated_at": p.updated_at
        } for p in policies
    ]


@router.get("/pricing/autonomy/decisions", response_model=List[dict])
def list_autonomy_decisions(
    limit: int = 50,
    session: Session = Depends(get_session)
):
    """자율 집행 의사결정 이력 조회"""
    from app.models import AutonomyDecisionLog
    logs = session.query(AutonomyDecisionLog).order_by(desc(AutonomyDecisionLog.created_at)).limit(limit).all()
    return [
        {
            "id": l.id,
            "recommendation_id": l.recommendation_id,
            "segment_key": l.segment_key,
            "tier_used": l.tier_used,
            "decision": l.decision,
            "reasons": l.reasons,
            "created_at": l.created_at
        } for l in logs
    ]
