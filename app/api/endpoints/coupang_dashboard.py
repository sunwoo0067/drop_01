from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc
from app.db import get_session
from app.models import AdaptivePolicyEvent, MarketListing
from app.services.analytics.coupang_stats import CoupangAnalyticsService
from app.services.analytics.coupang_policy import CoupangSourcingPolicyService
from typing import Any, List
from datetime import datetime, timedelta, timezone

router = APIRouter()

@router.get("/adaptive-stats")
def get_adaptive_dashboard_stats(
    session: Session = Depends(get_session),
) -> Any:
    """
    쿠팡 소싱 엔진의 지능화 지표 6대 카드를 반환합니다.
    """
    
    # 1. AR Trends (최근 7일 vs 전체)
    # (단순화를 위해 현재 메모리상에서 계산하거나 통계 서비스 호출)
    all_cats = CoupangAnalyticsService.get_category_approval_stats(session, days=365)
    recent_cats = CoupangAnalyticsService.get_category_approval_stats(session, days=7)
    
    avg_ar_365 = sum(c["approval_rate"] for c in all_cats) / len(all_cats) if all_cats else 0
    avg_ar_7 = sum(c["approval_rate"] for c in recent_cats) / len(recent_cats) if recent_cats else 0
    
    # 2. Status Distribution (현 시점 등급 분포)
    # 모든 활성 카테고리에 대해 정책 평가 (실시간 계산)
    status_dist = {"CORE": 0, "TRY": 0, "RESEARCH": 0, "BLOCK": 0}
    for cat in all_cats:
        policy = CoupangSourcingPolicyService.evaluate_category_policy(session, cat["category_code"])
        status_dist[policy["grade"]] += 1
        
    # 3. Drift Logs (최근 감점 이벤트)
    drift_logs = (
        session.execute(
            select(AdaptivePolicyEvent)
            .where(AdaptivePolicyEvent.event_type == "PENALTY")
            .order_by(desc(AdaptivePolicyEvent.created_at))
            .limit(10)
        )
        .scalars()
        .all()
    )
    
    # 4. Recovery Logs (최근 복원 이벤트)
    recovery_logs = (
        session.execute(
            select(AdaptivePolicyEvent)
            .where(AdaptivePolicyEvent.event_type == "RECOVERY")
            .order_by(desc(AdaptivePolicyEvent.created_at))
            .limit(10)
        )
        .scalars()
        .all()
    )
    
    # 5. Failure Analysis (에러 유형 분포 - 최근 7일)
    failure_modes = {"CRITICAL": 0, "WARNING": 0, "TRANSIENT": 0, "NONE": 0}
    for cat in recent_cats:
        analysis = CoupangAnalyticsService.get_category_failure_analysis(session, cat["category_code"])
        failure_modes[analysis["severity"]] += 1

    # 6. Actionable Guidelines (Next Action)
    ar_diff = avg_ar_7 - avg_ar_365
    guidelines = {
        "ar_trends": "최근 7일 승인율 하락 발견" if ar_diff < -5 else "승인율 안정 유지 중",
        "status_distribution": f"BLOCK 등급 {status_dist['BLOCK']}개 관찰됨" if status_dist["BLOCK"] > 0 else "전체 등급 분포 양호",
        "drift_logs": "감점된 카테고리에 대한 24h 쿨다운 모니터링 필요" if drift_logs else "최근 감점 이벤트 없음",
        "recovery_logs": "복구된 카테고리의 소싱량 자동 상향(Recommendation) 검토" if recovery_logs else "복구 대기 중인 카테고리 분석 필요",
        "failure_modes": "CRITICAL Hotspot 발견 - 해당 키워드군 수동 회피 권장" if failure_modes["CRITICAL"] > 0 else "치명적 시스템 오류 없음"
    }

    return {
        "ar_trends": {
            "avg_365d": round(avg_ar_365, 1),
            "avg_7d": round(avg_ar_7, 1),
            "diff": round(ar_diff, 1),
            "next_action": guidelines["ar_trends"]
        },
        "status_distribution": {
            "counts": status_dist,
            "next_action": guidelines["status_distribution"]
        },
        "drift_logs": {
            "events": [
                {
                    "category_code": log.category_code,
                    "multiplier": log.multiplier,
                    "severity": log.severity,
                    "reason": log.reason,
                    "created_at": log.created_at,
                    "top_reasons": log.top_rejection_reasons
                } for log in drift_logs
            ],
            "next_action": guidelines["drift_logs"]
        },
        "recovery_logs": {
            "events": [
                {
                    "category_code": log.category_code,
                    "multiplier": log.multiplier,
                    "reason": log.reason,
                    "created_at": log.created_at
                } for log in recovery_logs
            ],
            "next_action": guidelines["recovery_logs"]
        },
        "failure_modes": {
            "modes": failure_modes,
            "next_action": guidelines["failure_modes"]
        },
        "total_categories": len(all_cats),
        "policy_version": "1.2.0"
    }
