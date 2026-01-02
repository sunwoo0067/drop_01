from unittest.mock import patch, MagicMock
from app.services.analytics.coupang_policy import CoupangSourcingPolicyService
from datetime import datetime, timezone

def test_policy_with_mock():
    session = MagicMock()
    category_code = 'MOCK_CAT'
    
    # 1. 365일 통계 (좋음)
    mock_stats_365 = [
        {
            "category_code": category_code,
            "total_trials": 100,
            "success_count": 90,
            "exact_success_count": 80,
            "fallback_success_count": 10,
            "last_success_at": datetime.now(timezone.utc),
            "approval_rate": 90.0,
            "exact_rate": 80.0,
            "fallback_dependency": 11.1
        }
    ]
    
    # 2. 최근 7일 통계 (나쁨 - 10건 중 1건 성공)
    mock_stats_7 = [
        {
            "category_code": category_code,
            "total_trials": 10,
            "success_count": 1,
            "approval_rate": 10.0,
            "exact_rate": 10.0,
            "fallback_dependency": 0.0
        }
    ]

    with patch('app.services.analytics.coupang_stats.CoupangAnalyticsService.get_category_approval_stats') as mock_get_stats:
        # 첫 번째 호출(365일) -> 좋은 통계, 두 번째 호출(7일) -> 나쁜 통계
        mock_get_stats.side_effect = [mock_stats_365, mock_stats_7]
        
        print(f"--- Evaluating Policy for {category_code} with Mock Recent Failures ---")
        policy = CoupangSourcingPolicyService.evaluate_category_policy(session, category_code)
        
        print(f"Final Grade: {policy['grade']}")
        print(f"Final Score: {policy['score']}")
        print(f"Reason: {policy['reason']}")
        
        # 기대 결과: 최근 실패 페널티(x0.8)가 적용되어 점수 하락
        # 초기 AR 90.0 -> Penalty 적용 시 72.0
        # Score = (72 * 0.5) + (80 * 0.3) + ((100-11.1)*0.2) = 36 + 24 + 17.78 = 77.78 -> CORE? 
        # 아, AR이 72라도 ER이 높으면 CORE가 유지될 수 있음. 하지만 점수는 확실히 깎여야 함.
        # (만약 AR이 더 낮았다면 등급 하락까지 이어짐)

if __name__ == "__main__":
    test_policy_with_mock()
