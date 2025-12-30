import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from sqlalchemy import select, func, case, text
from sqlalchemy.orm import Session
from app.models import MarketListing, SourcingCandidate, Product
from app.settings import settings

logger = logging.getLogger(__name__)

class CoupangOperationalReportService:
    """
    쿠팡 소싱 정책 운영 지표(KPI)를 분석하고 보고서를 생성합니다.
    """
    
    @staticmethod
    def get_daily_operational_stats(session: Session, days: int = 7) -> Dict[str, Any]:
        """
        최근 N일간의 일일 소싱 및 등록 지표를 반환합니다.
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # 1. 등급 요약 (전체 분포)
        # SourcingCandidate.sourcing_policy -> {'grade': 'CORE', ...}
        # JSONB 필드 접근을 위해 SQL Expression 사용
        grade_query = (
            select(
                func.jsonb_extract_path_text(SourcingCandidate.sourcing_policy, 'grade').label('grade'),
                func.count(SourcingCandidate.id).label('count')
            )
            .where(SourcingCandidate.created_at >= start_date)
            .group_by(text('grade'))
        )
        grade_results = session.execute(grade_query).all()
        grade_distribution = {r.grade or "UNKNOWN": r.count for r in grade_results}
        
        # 2. 등록 퍼포먼스 (MarketListing)
        from app.models import MarketAccount
        listing_query = (
            select(
                func.count(MarketListing.id).label("total"),
                func.sum(case((MarketListing.status == "ACTIVE", 1), else_=0)).label("success"),
                func.sum(case((MarketListing.category_grade == "FALLBACK_SAFE", 1), else_=0)).label("fallback")
            )
            .join(MarketAccount, MarketListing.market_account_id == MarketAccount.id)
            .where(MarketAccount.market_code == "COUPANG")
            .where(MarketListing.linked_at >= start_date)
        )
        listing_res = session.execute(listing_query).one()
        total_attempted = listing_res.total or 0
        total_success = listing_res.success or 0
        total_fallback = listing_res.fallback or 0
        
        success_rate = (total_success / total_attempted * 100) if total_attempted > 0 else 0
        fallback_dependency = (total_fallback / total_success * 100) if total_success > 0 else 0
        
        # 3. 정책에 의한 스킵 통계
        # SourcingCandidate 중 status='REJECTED' 이면서 policy_decision.action='skip_coupang'인 것 (또는 필터링된 기록)
        # 현재 로직상 BLOCK은 execute_keyword_sourcing 단계에서 skip되므로 candidate가 안 생길 수 있음.
        # 하지만 _execute_create_candidate에 policy_decision을 넘기므로, skip된 경우도 기록되게 할 수 있음.
        # 일단 현재 DB에 쌓인 sourcing_policy 기반으로 BLOCK 비중 확인
        block_count = grade_distribution.get("BLOCK", 0)
        total_sourced = sum(grade_distribution.values())
        skip_rate = (block_count / total_sourced * 100) if total_sourced > 0 else 0

        # 4. 시계열 데이터 (최근 7일)
        time_series = []
        for i in range(days):
            target_date = (datetime.now(timezone.utc) - timedelta(days=i)).date()
            d_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            d_end = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)
            
            # 해당 일자 성공률
            d_query = (
                select(
                    func.count(MarketListing.id).label("total"),
                    func.sum(case((MarketListing.status == "ACTIVE", 1), else_=0)).label("success")
                )
                .join(MarketAccount, MarketListing.market_account_id == MarketAccount.id)
                .where(MarketAccount.market_code == "COUPANG")
                .where(MarketListing.linked_at >= d_start)
                .where(MarketListing.linked_at <= d_end)
            )
            d_res = session.execute(d_query).one()
            d_total = d_res.total or 0
            d_success = d_res.success or 0
            d_sr = (d_success / d_total * 100) if d_total > 0 else 0
            
            # 소싱 수량 (오늘)
            d_sourcing_query = (
                select(func.count(SourcingCandidate.id))
                .where(SourcingCandidate.created_at >= d_start)
                .where(SourcingCandidate.created_at <= d_end)
            )
            d_sourcing_total = session.scalar(d_sourcing_query) or 0
            
            time_series.append({
                "date": target_date.isoformat(),
                "attempted": d_total,
                "success_rate": round(d_sr, 1),
                "attempted_sourcing": d_sourcing_total,
                "block_count": session.scalar(
                    select(func.count(SourcingCandidate.id))
                    .where(SourcingCandidate.created_at >= d_start)
                    .where(SourcingCandidate.created_at <= d_end)
                    .where(func.jsonb_extract_path_text(SourcingCandidate.sourcing_policy, 'grade') == 'BLOCK')
                ) or 0
            })

        return {
            "summary": {
                "total_attempted": total_attempted,
                "success_rate": round(success_rate, 1),
                "fallback_dependency": round(fallback_dependency, 1),
                "skip_rate": round(skip_rate, 1),
                "current_mode": settings.coupang_sourcing_policy_mode,
                "stability_mode": settings.coupang_stability_mode
            },
            "grade_distribution": grade_distribution,
            "time_series": time_series
        }
