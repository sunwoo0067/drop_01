import asyncio
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from app.services.orchestrator_service import OrchestratorService
from app.services.analytics.strategy_drift import StrategyDriftDetector
from app.models import OrchestrationEvent

async def test_v140_strategic_autonomy():
    print("=== Coupang Strategic Autonomy v1.4.0 Verification ===")
    
    db = MagicMock()
    orchestrator = OrchestratorService(db)
    
    # Mocking system setting
    mock_setting = MagicMock()
    mock_setting.value = {"listing_limit": 1000}
    db.query.return_value.filter_by.return_value.one_or_none.return_value = mock_setting

    # 1. Scenario: ROI Collapse (Should Pivot)
    print("\n[Scenario 1] Strategic Pivot - ROI Collapse")
    
    with patch("app.services.analytics.strategy_drift.StrategyDriftDetector.analyze_global_strategy_health") as mock_health:
        mock_health.return_value = {
            "should_pivot": True,
            "message": "CRITICAL: ROI collapse detected",
            "severity": "CRITICAL",
            "current_roi": 0.05,
            "roi_velocity": -0.1
        }
        
        # We need to mock plan_seasonal_strategy as well to avoid actual AI calls
        with patch.object(orchestrator.ai_service, "plan_seasonal_strategy", return_value={"season_name": "Test", "strategy_theme": "Test"}):
            # Also mock run_continuous_processing and other background tasks
            with patch.object(orchestrator, "run_continuous_processing"), patch.object(orchestrator, "run_continuous_listing"):
                # Use dry_run=False to see the limit effect, but mock the actual side effects
                with patch.object(orchestrator.sourcing_agent, "find_cleanup_targets", return_value=[]):
                    await orchestrator.run_daily_cycle(dry_run=True)
                    
                    # Find the PLANNING SUCCESS event
                    planning_event = next((c[0][0] for c in db.add.call_args_list if isinstance(c[0][0], OrchestrationEvent) and c[0][0].step == "PLANNING" and c[0][0].status == "SUCCESS"), None)
                    print(f"Planning Event Message: {planning_event.message}")
                    assert "Limit: 500" in planning_event.message
                    print("✅ Scenario 1 Passed (Quota reduced by 50%)")

    # 2. Scenario: ROI Momentum (Should Boost)
    print("\n[Scenario 2] Strategic Momentum - High ROI")
    db.add.reset_mock()
    
    with patch("app.services.analytics.strategy_drift.StrategyDriftDetector.analyze_global_strategy_health") as mock_health:
        mock_health.return_value = {
            "should_pivot": False,
            "message": "Strategy Healthy",
            "severity": "INFO",
            "current_roi": 0.25,
            "roi_velocity": 0.05
        }
        
        with patch.object(orchestrator.ai_service, "plan_seasonal_strategy", return_value={"season_name": "Test", "strategy_theme": "Test"}):
             with patch.object(orchestrator, "run_continuous_processing"), patch.object(orchestrator, "run_continuous_listing"):
                 with patch.object(orchestrator.sourcing_agent, "find_cleanup_targets", return_value=[]):
                    await orchestrator.run_daily_cycle(dry_run=True)
                    
                    planning_event = next((c[0][0] for c in db.add.call_args_list if isinstance(c[0][0], OrchestrationEvent) and c[0][0].step == "PLANNING" and c[0][0].status == "SUCCESS"), None)
                    print(f"Planning Event Message: {planning_event.message}")
                    assert "Limit: 1200" in planning_event.message
                    print("✅ Scenario 2 Passed (Quota boosted by 20%)")

if __name__ == "__main__":
    asyncio.run(test_v140_strategic_autonomy())
