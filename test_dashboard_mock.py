from unittest.mock import MagicMock, patch
from app.api.endpoints.coupang_dashboard import get_adaptive_dashboard_stats
from datetime import datetime, timezone

def test_dashboard_api_mock():
    session = MagicMock()
    
    # 1. Mock Category Stats
    mock_all_cats = [
        {"category_code": "CAT_1", "approval_rate": 80.0},
        {"category_code": "CAT_2", "approval_rate": 30.0}
    ]
    mock_recent_cats = [
        {"category_code": "CAT_1", "approval_rate": 90.0},
        {"category_code": "CAT_2", "approval_rate": 10.0}
    ]
    
    # 2. Mock Failure Analysis
    mock_fail_1 = {"severity": "NONE", "penalty_score": 1.0}
    mock_fail_2 = {"severity": "CRITICAL", "penalty_score": 0.7}
    
    # 3. Mock Events
    mock_event = MagicMock()
    mock_event.category_code = "CAT_2"
    mock_event.multiplier = 0.7
    mock_event.severity = "CRITICAL"
    mock_event.reason = "Test Penalty"
    mock_event.created_at = datetime.now(timezone.utc)
    
    with patch('app.services.analytics.coupang_stats.CoupangAnalyticsService.get_category_approval_stats') as m_stats, \
         patch('app.services.analytics.coupang_stats.CoupangAnalyticsService.get_category_failure_analysis') as m_fail, \
         patch('app.services.analytics.coupang_policy.CoupangSourcingPolicyService.evaluate_category_policy') as m_policy:
        
        m_stats.side_effect = [mock_all_cats, mock_recent_cats]
        m_fail.side_effect = [mock_fail_1, mock_fail_2]
        
        # Policy Mocking
        m_policy.side_effect = [{"grade": "CORE"}, {"grade": "BLOCK"}]
        
        # Events Mocking
        session.execute().scalars().all.return_value = [mock_event]
        
        stats = get_adaptive_dashboard_stats(session)
        
        print("\n--- Dashboard API Mock Result ---")
        print(f"AR Trends: {stats['ar_trends']}")
        print(f"Status Dist: {stats['status_distribution']}")
        print(f"Failure Modes: {stats['failure_modes']}")
        print(f"Drift Logs Count: {len(stats['drift_logs'])}")
        
        # Verification
        assert stats['ar_trends']['avg_365d'] == 55.0 # (80+30)/2
        assert stats['ar_trends']['avg_7d'] == 50.0 # (90+10)/2
        assert stats['status_distribution']['counts']['CORE'] == 1
        assert stats['status_distribution']['counts']['BLOCK'] == 1
        print("Test Passed!")

if __name__ == "__main__":
    test_dashboard_api_mock()
