from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_session
from app.services.analytics.coupang_stats import CoupangAnalyticsService
from app.services.analytics.coupang_policy import CoupangSourcingPolicyService
from typing import Any, List

router = APIRouter()

@router.get("/recommendations")
def get_sourcing_recommendations(
    session: Session = Depends(get_session),
    limit: int = Query(default=10, ge=1, le=50)
) -> Any:
    """
    정책 등급과 점수를 기반으로 '오늘의 소싱 추천/회피 리스트'를 제공합니다.
    """
    all_stats = CoupangAnalyticsService.get_category_approval_stats(session, days=365)
    
    scored_items = []
    
    for stat in all_stats:
        cat_code = stat["category_code"]
        policy = CoupangSourcingPolicyService.evaluate_category_policy(session, cat_code)
        
        # 가중치 계산: Base Score * Adaptive Multiplier * Approval Rate Factor
        grade = policy["grade"]
        base_score = policy["score"]
        
        # 등급별 가중치 (Ranking용)
        grade_weight = {
            "CORE": 1.5,
            "TRY": 1.2,
            "RESEARCH": 1.0,
            "BLOCK": 0.0
        }.get(grade, 1.0)
        
        final_rank_score = base_score * grade_weight
        
        scored_items.append({
            "category_code": cat_code,
            "grade": grade,
            "score": base_score,
            "rank_score": round(final_rank_score, 2),
            "reason": policy["reason"],
            "ar": stat["approval_rate"]
        })
        
    # 랭킹 정렬
    scored_items.sort(key=lambda x: x["rank_score"], reverse=True)
    
    recommendations = [item for item in scored_items if item["grade"] in ["CORE", "TRY"]][:limit]
    avoidance_list = [item for item in scored_items if item["grade"] == "BLOCK"][:limit]
    
    return {
        "today_recommendations": recommendations,
        "avoidance_list": avoidance_list,
        "summary": {
            "recommended_count": len(recommendations),
            "avoidance_count": len(avoidance_list),
            "strategy": "CORE/TRY 등급 중심의 안전 소싱 및 하이리스크 카테고리 회피"
        }
    }
