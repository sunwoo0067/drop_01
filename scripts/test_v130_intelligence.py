import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from app.services.analytics.coupang_policy import CoupangSourcingPolicyService
from app.services.analytics.drift_detector import CoupangDriftDetectorService
from app.services.analytics.coupang_stats import CoupangAnalyticsService

def test_v130_features():
    print("=== Coupang Intelligence v1.3.0 Verification ===")
    
    session = MagicMock()
    
    # helper to reset mocks
    def reset_operator_mock(val=None):
        session.execute.return_value.scalar_one_or_none.return_value = val

    # 1. Scenario 1: Severe Drift (Safety Check)
    reset_operator_mock(None)
    category_severe = "SEVERE_DRIFT_CAT"
    def mock_stats_severe(session, days, offset_days=0):
        if offset_days == 0:
            return [{"category_code": category_severe, "approval_rate": 40.0, "total_trials": 10, "exact_rate": 40.0, "fallback_dependency": 10.0, "last_success_at": datetime.now(timezone.utc)}]
        else:
            return [{"category_code": category_severe, "approval_rate": 80.0, "total_trials": 10, "exact_rate": 80.0, "fallback_dependency": 0.0, "last_success_at": datetime.now(timezone.utc) - timedelta(days=4)}]

    CoupangAnalyticsService.get_category_approval_stats = mock_stats_severe
    CoupangAnalyticsService.get_category_roi_stats = MagicMock(return_value={category_severe: {"roi": 0.4, "revenue": 1000000}})
    
    print(f"\n[Scenario 1] Severe Drift (80% -> 40%)")
    policy_severe = CoupangSourcingPolicyService.evaluate_category_policy(session, category_severe)
    print(f"Grade: {policy_severe['grade']}, Score: {policy_severe['score']}")
    assert policy_severe['grade'] == "BLOCK"
    print("✅ Scenario 1 Passed (Hard Gate Blocked correctly)")

    # 2. Scenario 2: Mild Drift + High ROI (Resilience)
    reset_operator_mock(None)
    category_mild = "MILD_DRIFT_CAT"
    def mock_stats_mild(session, days, offset_days=0):
        if offset_days == 0:
            return [{"category_code": category_mild, "approval_rate": 70.0, "total_trials": 20, "exact_rate": 60.0, "fallback_dependency": 5.0, "last_success_at": datetime.now(timezone.utc)}]
        else:
            return [{"category_code": category_mild, "approval_rate": 90.0, "total_trials": 20, "exact_rate": 80.0, "fallback_dependency": 0.0, "last_success_at": datetime.now(timezone.utc) - timedelta(days=4)}]

    CoupangAnalyticsService.get_category_approval_stats = mock_stats_mild
    CoupangAnalyticsService.get_category_roi_stats = MagicMock(return_value={category_mild: {"roi": 0.4, "revenue": 1000000}})
    
    print(f"\n[Scenario 2] Mild Drift (90% -> 70%) + High ROI (40%)")
    policy_mild = CoupangSourcingPolicyService.evaluate_category_policy(session, category_mild)
    print(f"Grade: {policy_mild['grade']}, Score: {policy_mild['score']}")
    assert abs(policy_mild['score'] - 73.9) < 0.1
    print("✅ Scenario 2 Passed (Survived drift due to High ROI boost)")

    # 3. Scenario 3: Baseline (No Sales, No Drift)
    reset_operator_mock(None)
    category_base = "BASE_CAT"
    def mock_stats_base(session, days, offset_days=0):
        return [{"category_code": category_base, "approval_rate": 80.0, "total_trials": 20, "exact_rate": 70.0, "fallback_dependency": 0.0, "last_success_at": datetime.now(timezone.utc)}]
    
    CoupangAnalyticsService.get_category_approval_stats = mock_stats_base
    CoupangAnalyticsService.get_category_roi_stats = MagicMock(return_value={}) # No data
    
    print(f"\n[Scenario 3] Baseline (80% AR, No Sales Data)")
    policy_base = CoupangSourcingPolicyService.evaluate_category_policy(session, category_base)
    print(f"Grade: {policy_base['grade']}, Score: {policy_base['score']}")
    assert policy_base['score'] == 71.0
    print("✅ Scenario 3 Passed (Neutral ROI weight)")

    # 4. Scenario 4: Human-in-the-loop (Operator UP)
    # Baseline 80% AR category + Operator UP (1.2 multiplier)
    print(f"\n[Scenario 4] Operator Feedback (UP: 1.2x)")
    
    from app.models import AdaptivePolicyEvent
    mock_operator_event = MagicMock(spec=AdaptivePolicyEvent)
    mock_operator_event.multiplier = 1.2
    reset_operator_mock(mock_operator_event)
    
    policy_op = CoupangSourcingPolicyService.evaluate_category_policy(session, category_base)
    print(f"Grade: {policy_op['grade']}, Score: {policy_op['score']}")
    assert policy_op['score'] == 77.4
    print("✅ Scenario 4 Passed (Operator UP correctly boosted score)")

if __name__ == "__main__":
    test_v130_features()
