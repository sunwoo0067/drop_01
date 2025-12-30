import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models import MarketListing
from app.settings import settings
from app.services.analytics.coupang_stats import CoupangAnalyticsService

from app.services.analytics.drift_detector import CoupangDriftDetectorService

logger = logging.getLogger(__name__)

POLICY_VERSION = "1.3.0" # Advanced Cognitive (Season Drift + ROI)

class CoupangSourcingPolicyService:
    @staticmethod
    def log_policy_event(
        session: Session, 
        category_code: str, 
        event_type: str, 
        multiplier: float, 
        reason: str, 
        severity: str = "NONE", 
        context: dict = None,
        window_days: int = 7
    ):
        """
        정책 변경 이벤트를 DB에 기록합니다. (스로틀링 포함)
        """
        from app.models import AdaptivePolicyEvent
        
        # 1. Throttling: 동일 카테고리/이벤트 타입에 대해 최근 6시간 내 기록이 있으면 스킵 (진동 방지)
        throttle_limit = datetime.now(timezone.utc) - timedelta(hours=6)
        existing = session.execute(
            select(AdaptivePolicyEvent)
            .where(AdaptivePolicyEvent.category_code == category_code)
            .where(AdaptivePolicyEvent.event_type == event_type)
            .where(AdaptivePolicyEvent.created_at >= throttle_limit)
        ).scalars().first()
        
        if existing:
            return

        window_end = datetime.now(timezone.utc)
        window_start = window_end - timedelta(days=window_days)
        
        rejection_reasons = []
        if context and "top_rejection_reasons" in context:
            rejection_reasons = context["top_rejection_reasons"]

        event = AdaptivePolicyEvent(
            category_code=category_code,
            event_type=event_type,
            severity=severity,
            multiplier=multiplier,
            reason=reason,
            context=context,
            policy_version=POLICY_VERSION,
            window_start=window_start,
            window_end=window_end,
            top_rejection_reasons=rejection_reasons
        )
        session.add(event)
        session.flush()

    @staticmethod
    def evaluate_category_policy(session: Session, category_code: str) -> dict[str, Any]:
        """
        특정 카테고리에 대한 소싱 정책을 평가합니다. (Option C 핵심 로직)
        """
        # 365일 데이터를 기준으로 넓은 표본 확보
        stats_list = CoupangAnalyticsService.get_category_approval_stats(session, days=365)
        stat = next((s for s in stats_list if s["category_code"] == category_code), None)
        
        if not stat:
            # 데이터가 아예 없는 경우 실험군(RESEARCH)으로 시작
            return {
                "category_code": category_code,
                "grade": "RESEARCH",
                "score": 50,
                "reason": "신규 카테고리 (데이터 없음)",
                "details": {}
            }
            
        ar = stat["approval_rate"]
        er = stat["exact_rate"]
        fd = stat["fallback_dependency"]
        total = stat["total_trials"]
        last_success_at = stat["last_success_at"]
        
        # 1. 시간 가중치 (90일 초과 시 30% 감쇄)
        time_penalty = 1.0
        if last_success_at:
            if datetime.now(timezone.utc) - last_success_at > timedelta(days=90):
                time_penalty = 0.7
                ar *= time_penalty
                er *= time_penalty

        # 1.1 최근 성과 가중치 (Recent Performance Adjustment - 7 Days)
        # 최신 데이터에 더 민감하게 반응하여 지능화 (Adaptive Intelligence)
        recent_stats_list = CoupangAnalyticsService.get_category_approval_stats(session, days=7)
        recent_stat = next((s for s in recent_stats_list if s["category_code"] == category_code), None)
        
        adaptive_multiplier = 1.0
        
        if recent_stat:
            recent_ar = recent_stat["approval_rate"]
            recent_total = recent_stat["total_trials"]
            
            # (1) Recovery & Excellence Boost: Hysteresis 적용
            # 감점(40% 미만)보다 복구(75% 이상) 조건을 더 까다롭게 설정하여 보수적 운영
            unique_products = recent_stat.get("unique_product_count", 0)
            days_distributed = recent_stat.get("days_distributed", 0)
            
            if recent_total >= 5 and recent_ar >= 75 and (unique_products >= 3 or days_distributed >= 2):
                adaptive_multiplier = 1.1
                logger.info(f"Recovery/Excellence Boost (Hysteresis): {category_code} (7d AR={recent_ar:.1f}% >= 75%, Prod={unique_products}, Days={days_distributed})")
                CoupangSourcingPolicyService.log_policy_event(
                    session, category_code, "RECOVERY", 1.1, 
                    f"최근 성과 우수 및 안정 (7일 AR={recent_ar:.1f}%, 보수적 복구 기준 달성)",
                    context=recent_stat
                )
            
            # (2) Weighted Failure Penalty: 등록 실패 원인에 따른 가중 감점
            elif recent_total >= 3 and recent_ar < 40:
                failure_analysis = CoupangAnalyticsService.get_category_failure_analysis(session, category_code)
                weight = failure_analysis.get("penalty_score", 0.8)
                adaptive_multiplier = weight
                logger.warning(f"Weighted Failure Penalty: {category_code} (7d AR={recent_ar:.1f}%, weight={weight:.2f}, severity={failure_analysis['severity']})")
                
                CoupangSourcingPolicyService.log_policy_event(
                    session, category_code, "PENALTY", weight, 
                    f"최근 성과 저조 ({failure_analysis['severity']} 에러 포함)",
                    severity=failure_analysis["severity"],
                    context={**recent_stat, **failure_analysis}
                )

        ar *= adaptive_multiplier

        # 1.2 Season Drift Detection: 성과 하락 추세 감지 및 추가 감점
        drift_multiplier = 1.0
        drift_result = CoupangDriftDetectorService.analyze_category_drift(session, category_code, days=3)
        if drift_result.get("is_drift"):
            drift_multiplier = 0.8 if drift_result["severity"] == "WARNING" else 0.5
            logger.warning(f"Season Drift Detected: {category_code} (Velocity={drift_result['velocity']}, Multiplier={drift_multiplier})")

        ar *= drift_multiplier

        # 1.3 Operator Feedback (v1.3.0): 운영자 수동 피드백 반영 (Human-in-the-loop)
        # 7일 이내의 가장 최근 운영자 신호를 적용합니다.
        from app.models import AdaptivePolicyEvent
        operator_event = session.execute(
            select(AdaptivePolicyEvent)
            .where(AdaptivePolicyEvent.category_code == category_code)
            .where(AdaptivePolicyEvent.event_type.in_(["OPERATOR_UP", "OPERATOR_DOWN"]))
            .where(AdaptivePolicyEvent.created_at >= datetime.now(timezone.utc) - timedelta(days=7))
            .order_by(AdaptivePolicyEvent.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        
        operator_multiplier = 1.0
        if operator_event:
            operator_multiplier = operator_event.multiplier
            logger.info(f"Operator Feedback Applied: {category_code} (Multiplier={operator_multiplier})")
        
        ar *= operator_multiplier

        # 1.4 ROI Weighting (v1.3.0): 실질 수익성 지표 반영
        # 수익 데이터가 있는 경우 가중치 부여, 없는 경우 중립 점수(50) 기준
        roi_stats = CoupangAnalyticsService.get_category_roi_stats(session, days=90)
        roi_info = roi_stats.get(category_code, {"roi": 0.0, "revenue": 0})
        
        roi = roi_info["roi"]
        # ROI Score: 0.15(15%)를 50점으로 기준, 0.4(40%) 이상이면 100점, 0 이하면 0점
        roi_score = min(100, max(0, (roi * 250) + 12.5)) if roi_info["revenue"] > 0 else 50
        
        # 2. Hard Gate 필터
        if ar < 40 or fd > 80:
            return {
                "category_code": category_code,
                "grade": "BLOCK",
                "score": 0,
                "reason": f"Hard Gate 차단 (승인율 {ar:.1f}% < 40% 또는 우회의존도 {fd:.1f}% > 80%)",
                "details": stat
            }
            
        # 3. 최소 데이터 보호장치
        if total < 5:
            return {
                "category_code": category_code,
                "grade": "RESEARCH",
                "score": 45,
                "reason": f"데이터 부족 (시도 {total}건 < 5건)",
                "details": stat
            }
            
        # 4. 소싱 점수 계산 (v1.3.0 Optimized Formula)
        # SourcingScore = (AR * 0.4) + (ER * 0.2) + ((100-FD) * 0.1) + (ROI_Score * 0.3)
        score = (ar * 0.4) + (er * 0.2) + ((100 - fd) * 0.1) + (roi_score * 0.3)
        
        # 5. 등급 분류
        if score >= 70:
            grade = "CORE"
            reason = "적극 소싱 가능 (높은 승인율 및 검증 데이터)"
        elif score >= 55:
            grade = "TRY"
            reason = "제한적 소싱 권장"
        elif score >= 40:
            grade = "RESEARCH"
            reason = "실험적 소싱 (데이터 축적 필요)"
        else:
            grade = "BLOCK"
            reason = "낮은 소싱 점수로 인한 제외"
            
        return {
            "category_code": category_code,
            "grade": grade,
            "score": round(score, 1),
            "reason": reason,
            "details": stat
        }

    @staticmethod
    def get_all_policies(session: Session):
        """
        모든 활성 카테고리에 대한 정책 리포트를 생성합니다.
        """
        stats_list = CoupangAnalyticsService.get_category_approval_stats(session, days=365)
        policies = []
        for s in stats_list:
            policies.append(CoupangSourcingPolicyService.evaluate_category_policy(session, s["category_code"]))
        
        # 점수 높은 순 정렬
        policies.sort(key=lambda x: x["score"], reverse=True)
        return policies

    @staticmethod
    def evaluate_keyword_policy(session: Session, keyword: str) -> dict[str, Any]:
        """
        키워드 기반 소싱 정책을 평가합니다. (Option C 키워드 역매핑)
        해당 키워드로 등록된 상품들이 속한 카테고리들의 점수를 종합합니다.
        """
        from app.models import Product
        
        # 해당 키워드를 포함하는 상품들이 속한 카테고리 조회
        categories_query = (
            select(MarketListing.category_code)
            .join(Product, MarketListing.product_id == Product.id)
            .where((Product.name.contains(keyword)) | (Product.processed_name.contains(keyword)))
            .where(MarketListing.category_code != None)
            .distinct()
        )
        category_codes = session.execute(categories_query).scalars().all()
        
        if not category_codes:
            # 1. Accelerated Learning (신규 키워드 가속): BenchmarkProduct(외부 데이터)에서 카테고리 유추
            from app.models import BenchmarkProduct
            bench_query = (
                select(BenchmarkProduct.category_path)
                .where(BenchmarkProduct.name.contains(keyword))
                .where(BenchmarkProduct.market_code == "COUPANG")
                .limit(20)
            )
            bench_paths = session.execute(bench_query).scalars().all()
            
            if bench_paths:
                # 경로에서 말단 카테고리 이름을 추출하여 기존 통계와 매칭 시도
                # 예: "주방용품 > 그릇 > 공기" -> "공기"
                potential_cat_names = set()
                for path in bench_paths:
                    parts = [p.strip() for p in path.split(">")]
                    if parts:
                        potential_cat_names.add(parts[-1])
                
                # 추출된 카테고리 이름으로 내부 통계(category_code) 찾기
                # (현실적으로는 별도의 매핑 테이블이나 검색이 필요하지만, 여기서는 heuristics 적용)
                # 우선은 "데이터 없음"으로 리턴하되, 로그에 기록하여 수동 검토 지원
                logger.info(f"신규 키워드 '{keyword}'에 대해 외부 데이터 기반 카테고리 유추됨: {potential_cat_names}")

            return {
                "keyword": keyword,
                "grade": "RESEARCH",
                "score": 50,
                "reason": "신규 키워드 (기존 데이터 없음)",
                "involved_categories": []
            }
            
        category_policies = [
            CoupangSourcingPolicyService.evaluate_category_policy(session, code)
            for code in category_codes
        ]
        
        # 1. 최고 점수 추출 및 BLOCK 카테고리 포함 시 감점(-10)
        max_score = max(p["score"] for p in category_policies)
        has_block = any(p["grade"] == "BLOCK" for p in category_policies)
        
        final_score = max_score
        if has_block:
            final_score -= 10
            
        # 2. 최종 등급 결정 (0점 하한선)
        final_score = max(0, final_score)
        
        if final_score >= 70: grade = "CORE"
        elif final_score >= 55: grade = "TRY"
        elif final_score >= 40: grade = "RESEARCH"
        else: grade = "BLOCK"
        
        return {
            "keyword": keyword,
            "grade": grade,
            "score": round(final_score, 1),
            "reason": f"키워드 관련 카테고리({len(category_policies)}개) 종합 평가 (BLOCK 포함 감점: {has_block})",
            "involved_categories": [p["category_code"] for p in category_policies]
        }

    @staticmethod
    def get_action_from_policy(policy: dict[str, Any]) -> dict[str, Any]:
        """
        정책 평가 결과와 현재 운영 모드(shadow/enforce_lite/enforce)를 결합하여 최종 액션을 결정합니다.
        """
        mode = settings.coupang_sourcing_policy_mode
        grade = policy["grade"]
        score = policy["score"]
        
        # 기본값 (CORE/TRY 기준)
        max_items = 50 if grade == "CORE" else 10
        action = "normal"
        force_research = False
        allowed_markets = ["coupang", "naver"]
        
        if grade == "BLOCK":
            if mode == "enforce" or mode == "enforce_lite":
                action = "skip_coupang"
                allowed_markets = ["naver"]
                max_items = 100 # 네이버 전용으로 전환 시 수량 제한 해제 시도 가능
            else:
                action = "shadow_block" # shadow 모드에서는 로깅만 하고 진행
                
        elif grade == "RESEARCH":
            max_items = 3
            force_research = True
            if mode == "enforce" or mode == "enforce_lite":
                action = "limit_sourcing"
            else:
                action = "shadow_limit"

        return {
            "mode": mode,
            "grade": grade,
            "score": score,
            "action": action,
            "max_items": max_items,
            "allowed_markets": allowed_markets,
            "force_research": force_research,
            "policy_reason": policy["reason"]
        }
