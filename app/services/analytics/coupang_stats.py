import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import func, select, case, text
from sqlalchemy.orm import Session
from app.models import MarketListing, Product

class CoupangAnalyticsService:
    @staticmethod
    def get_category_approval_stats(session: Session, days: int = 30):
        """
        카테고리별 승인율 및 운영 지표를 계산합니다.
        (Option C의 핵심 데이터 소스)
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        query = (
            select(
                MarketListing.category_code,
                func.count(MarketListing.id).label("total_trials"),
                func.sum(case((MarketListing.status == "ACTIVE", 1), else_=0)).label("success_count"),
                func.sum(case((MarketListing.category_grade == "VERIFIED_EXACT", 1), else_=0)).label("exact_success_count"),
                func.sum(case((MarketListing.category_grade == "FALLBACK_SAFE", 1), else_=0)).label("fallback_success_count"),
                func.max(case((MarketListing.status == "ACTIVE", MarketListing.linked_at), else_=None)).label("last_success_at")
            )
            .where(MarketListing.linked_at >= start_date)
            .group_by(MarketListing.category_code)
        )
        
        results = session.execute(query).all()
        
        stats = []
        for r in results:
            if not r.category_code:
                continue
                
            total = r.total_trials or 0
            success = r.success_count or 0
            exact = r.exact_success_count or 0
            fallback = r.fallback_success_count or 0
            last_success_at = r.last_success_at
            
            # KPI 계산 (0-100 scale로 변환)
            approval_rate = (success / total * 100) if total > 0 else 0
            exact_rate = (exact / total * 100) if total > 0 else 0
            fallback_dependency = (fallback / success * 100) if success > 0 else 0
            
            # 최근 성과 세부 지표 (다양성 체크용)
            unique_products = (
                session.execute(
                    select(func.count(func.distinct(MarketListing.product_id)))
                    .where(MarketListing.category_code == r.category_code)
                    .where(MarketListing.linked_at >= start_date)
                ).scalar() or 0
            )
            
            days_count = (
                session.execute(
                    select(func.count(func.distinct(func.date(MarketListing.linked_at))))
                    .where(MarketListing.category_code == r.category_code)
                    .where(MarketListing.linked_at >= start_date)
                ).scalar() or 0
            )

            stats.append({
                "category_code": r.category_code,
                "total_trials": total,
                "success_count": success,
                "exact_success_count": exact,
                "fallback_success_count": fallback,
                "last_success_at": last_success_at,
                "approval_rate": round(approval_rate, 2),
                "exact_rate": round(exact_rate, 2),
                "fallback_dependency": round(fallback_dependency, 2),
                "unique_product_count": unique_products,
                "days_distributed": days_count
            })
            
        # 승인율 높은 순으로 정렬
        stats.sort(key=lambda x: x["approval_rate"], reverse=True)
        return stats

    @staticmethod
    def get_category_failure_analysis(session: Session, category_code: str, days: int = 7):
        """
        특정 카테고리의 최근 실패 원인을 분석하여 리스크 유형을 분류합니다.
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        failures = (
            session.execute(
                select(MarketListing.rejection_reason)
                .where(MarketListing.category_code == category_code)
                .where(MarketListing.status == "DENIED")
                .where(MarketListing.linked_at >= start_date)
            )
            .scalars()
            .all()
        )
        
        if not failures:
            return {"severity": "NONE", "score": 1.0}
            
        critical_keywords = ["유통경로", "상표권", "브랜드소명", "미비", "불가", "인증", "금지"]
        warning_keywords = ["이미지", "상세", "옵션", "고시"]
        transient_keywords = ["timeout", "server", "temporary", "service unavailable", "429", "503"]
        
        critical_count = 0
        warning_count = 0
        transient_count = 0
        
        for reason_dict in failures:
            reason_str = str(reason_dict).lower()
            if any(kw in reason_str for kw in critical_keywords):
                critical_count += 1
            elif any(kw in reason_str for kw in transient_keywords):
                transient_count += 1
            elif any(kw in reason_str for kw in warning_keywords):
                warning_count += 1
                
        total = len(failures)
        # 가중치 계산 (1.0에서 감점)
        # TRANSIENT는 감점 대상에서 사실상 제외하거나 0.98 정도로 매우 약하게 처리
        penalty_score = 1.0 - (critical_count * 0.1) - (warning_count * 0.05) - (transient_count * 0.01)
        
        severity = "NONE"
        if critical_count > 0: severity = "CRITICAL"
        elif warning_count > 0: severity = "WARNING"
        elif transient_count > 0: severity = "TRANSIENT"
        
        # 상위 거절 사유 추출 (인간 가독성용)
        top_reasons = []
        for f in failures[:3]:
            msg = f.get("message", "알 수 없는 오류")
            if msg not in top_reasons:
                top_reasons.append(msg)

        return {
            "severity": severity,
            "penalty_score": max(0.6, penalty_score),
            "critical_count": critical_count,
            "warning_count": warning_count,
            "transient_count": transient_count,
            "total_failures": total,
            "top_rejection_reasons": top_reasons
        }

    @staticmethod
    def get_sourcing_priority_categories(session: Session, min_trials: int = 5):
        """
        승인율이 높고 검증된(Exact) 비중이 높은 우선순위 카테고리를 반환합니다.
        """
        all_stats = CoupangAnalyticsService.get_category_approval_stats(session)
        
        # 최소 시도 횟수 이상이며, 승인율이 70% 이상인 카테고리 필터링
        priority = [
            s for s in all_stats 
            if s["total_trials"] >= min_trials and s["approval_rate"] >= 0.7
        ]
        
        return priority
