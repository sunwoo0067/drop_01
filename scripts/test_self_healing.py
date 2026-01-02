from unittest.mock import patch, MagicMock
from app.services.analytics.coupang_policy import CoupangSourcingPolicyService
from datetime import datetime, timezone

def test_recovery_and_weighted_penalty():
    session = MagicMock()
    category_code = 'HEAL_CAT'
    
    # 1. 기초 통계 (AR 50%)
    mock_stats_365 = [{
        "category_code": category_code,
        "total_trials": 100,
        "success_count": 50,
        "exact_success_count": 40,
        "fallback_success_count": 10,
        "last_success_at": datetime.now(timezone.utc),
        "approval_rate": 50.0,
        "exact_rate": 40.0,
        "fallback_dependency": 20.0
    }]

    # Case A: Recovery (최근 5건 모두 성공)
    mock_stats_7_recovery = [{
        "category_code": category_code,
        "total_trials": 5,
        "success_count": 5,
        "approval_rate": 100.0
    }]

    # Case B: Weighted Penalty (치명적 에러)
    mock_stats_7_failure = [{
        "category_code": category_code,
        "total_trials": 3,
        "success_count": 0,
        "approval_rate": 0.0
    }]
    mock_failure_analysis_critical = {
        "severity": "CRITICAL",
        "penalty_score": 0.7 # 치명적
    }

    with patch('app.services.analytics.coupang_stats.CoupangAnalyticsService.get_category_approval_stats') as mock_get_stats:
        with patch('app.services.analytics.coupang_stats.CoupangAnalyticsService.get_category_failure_analysis') as mock_get_fail:
            
            # --- Test A: Recovery ---
            mock_get_stats.side_effect = [mock_stats_365, mock_stats_7_recovery]
            p_a = CoupangSourcingPolicyService.evaluate_category_policy(session, category_code)
            print(f"CASE A (Recovery) -> Score: {p_a['score']} (Should be boosted)")

            # --- Test B: Weighted Penalty ---
            mock_get_stats.side_effect = [mock_stats_365, mock_stats_7_failure]
            mock_get_fail.return_value = mock_failure_analysis_critical
            p_b = CoupangSourcingPolicyService.evaluate_category_policy(session, category_code)
            print(f"CASE B (Critical) -> Score: {p_b['score']}, Grade: {p_b['grade']} (Should be penalized hard)")

if __name__ == "__main__":
    test_recovery_and_weighted_penalty()
