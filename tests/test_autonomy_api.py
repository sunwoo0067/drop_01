"""
자율성 거버넌스 API 단위 테스트

자율성 정책, 의사결정 로그, 킬스위치 API를 테스트합니다.
"""
import pytest
from unittest.mock import Mock, patch
from uuid import uuid4
from sqlalchemy.orm import Session

from app.api.endpoints.autonomy import (
    list_autonomy_policies,
    get_autonomy_policy,
    update_autonomy_policy,
    create_autonomy_policy,
    list_autonomy_decision_logs,
    get_segment_stats,
    get_processing_kill_switch,
    set_processing_kill_switch,
    get_pricing_kill_switch,
    set_pricing_kill_switch,
    run_autonomy_tuner,
)
from app.models import AutonomyPolicy, AutonomyDecisionLog, SystemSetting
from app.services.pricing.segment_resolver import SegmentResolver


@pytest.fixture
def mock_db():
    """모의 DB 세션"""
    return Mock(spec=Session)


@pytest.fixture
def mock_policy():
    """테스트용 모의 자율성 정책"""
    policy = Mock(spec=AutonomyPolicy)
    policy.id = uuid4()
    policy.segment_key = "test_segment_key"
    policy.vendor = "ownerclan"
    policy.channel = "COUPANG"
    policy.category_code = "TEST"
    policy.strategy_id = uuid4()
    policy.lifecycle_stage = "STEP_1"
    policy.tier = 1
    policy.status = "ACTIVE"
    policy.config_override = None
    policy.created_at = Mock()
    policy.updated_at = Mock()
    return policy


class TestAutonomyPolicies:
    """자율성 정책 API 테스트"""

    def test_list_policies_returns_list(self, mock_db):
        """정책 목록 조회 테스트"""
        with patch('app.api.endpoints.autonomy.select') as mock_select:
            mock_query = Mock()
            mock_select.return_value.where.return_value.order_by.return_value.limit.return_value.scalars.return_value.all.return_value = []
            
            result = list_autonomy_policies(session=mock_db)
            
            assert isinstance(result, list)
            assert result == []

    def test_list_policies_with_filters(self, mock_db):
        """필터가 포함된 정책 목록 조회 테스트"""
        with patch('app.api.endpoints.autonomy.select') as mock_select:
            mock_query = Mock()
            mock_scalars = Mock()
            mock_scalars.all.return_value = []
            
            # 체이닝 테스트
            mock_select.return_value.where = Mock(return_value=mock_query)
            mock_query.where.return_value.order_by = Mock(return_value=mock_query)
            mock_query.order_by.return_value.limit = Mock(return_value=mock_query)
            mock_query.limit.return_value.scalars = Mock(return_value=mock_scalars)
            
            result = list_autonomy_policies(
                session=mock_db,
                status="ACTIVE",
                tier=1,
                limit=50
            )
            
            assert isinstance(result, list)

    def test_get_policy_by_id_success(self, mock_db, mock_policy):
        """정책 ID로 조회 성공 테스트"""
        with patch.object(mock_db, 'get', return_value=mock_policy):
            result = get_autonomy_policy(
                policy_id=mock_policy.id,
                session=mock_db
            )
            
            assert result.id == str(mock_policy.id)
            assert result.segment_key == mock_policy.segment_key
            assert result.tier == mock_policy.tier

    def test_get_policy_by_id_not_found(self, mock_db):
        """정책 ID로 조회 실패 테스트 (404)"""
        with patch.object(mock_db, 'get', return_value=None):
            with pytest.raises(Exception) as exc_info:
                get_autonomy_policy(policy_id=uuid4(), session=mock_db)
            
            assert "404" in str(exc_info.value)

    def test_update_policy_success(self, mock_db, mock_policy):
        """정책 업데이트 성공 테스트"""
        with patch.object(mock_db, 'get', return_value=mock_policy):
            with patch.object(mock_db, 'commit'):
                from app.api.endpoints.autonomy import AutonomyPolicyUpdateIn
                payload = AutonomyPolicyUpdateIn(tier=2, status="ACTIVE")
                
                result = update_autonomy_policy(
                    policy_id=mock_policy.id,
                    payload=payload,
                    session=mock_db
                )
                
                assert result.tier == 2

    def test_update_policy_invalid_tier(self, mock_db, mock_policy):
        """잘못된 티어로 업데이트 시 에러 테스트 (400)"""
        with patch.object(mock_db, 'get', return_value=mock_policy):
            from app.api.endpoints.autonomy import AutonomyPolicyUpdateIn
            payload = AutonomyPolicyUpdateIn(tier=5)  # 잘못된 티어
            
            with pytest.raises(Exception) as exc_info:
                update_autonomy_policy(
                    policy_id=mock_policy.id,
                    payload=payload,
                    session=mock_db
                )
            
            assert "400" in str(exc_info.value)

    def test_create_policy_success(self, mock_db):
        """새 정책 생성 성공 테스트"""
        test_segment_key = "v:ownerclan|ch:COUPANG|cat:TEST|st:STEP_1|lc:NULL"
        
        with patch('app.api.endpoints.autonomy.select') as mock_select:
            mock_execute = Mock()
            mock_execute.return_value.scalars.return_value.first.return_value = None  # 중복 없음
            
            with patch.object(mock_db, 'add'):
                with patch.object(mock_db, 'commit'):
                    policy_id = uuid4()
                    
                    # 모의 add 메서드로 ID 설정
                    def mock_add(obj):
                        obj.id = policy_id
                    mock_db.add.side_effect = mock_add
                    
                    result = create_autonomy_policy(
                        vendor="ownerclan",
                        channel="COUPANG",
                        category_code="TEST",
                        lifecycle_stage="STEP_1",
                        tier=1,
                        session=mock_db
                    )
                    
                    assert result.id == str(policy_id)
                    assert result.segment_key == test_segment_key

    def test_create_policy_duplicate(self, mock_db):
        """중복 세그먼트로 생성 시 에러 테스트 (400)"""
        test_segment_key = "v:ownerclan|ch:COUPANG|cat:TEST|st:STEP_1|lc:NULL"
        
        with patch('app.api.endpoints.autonomy.select') as mock_select:
            mock_execute = Mock()
            mock_execute.return_value.scalars.return_value.first.return_value = Mock(spec=AutonomyPolicy)  # 이미 존재
            
            with pytest.raises(Exception) as exc_info:
                create_autonomy_policy(
                    vendor="ownerclan",
                    channel="COUPANG",
                    category_code="TEST",
                    lifecycle_stage="STEP_1",
                    tier=1,
                    session=mock_db
                )
            
            assert "400" in str(exc_info.value)
            assert "이미 존재하는 세그먼트" in str(exc_info.value)


class TestAutonomyDecisionLogs:
    """자율적 의사결정 로그 API 테스트"""

    def test_list_decision_logs_returns_list(self, mock_db):
        """의사결정 로그 목록 조회 테스트"""
        with patch('app.api.endpoints.autonomy.select') as mock_select:
            mock_scalars = Mock()
            mock_scalars.all.return_value = []
            
            mock_select.return_value.order_by.return_value.limit.return_value.scalars = Mock(return_value=mock_scalars)
            
            result = list_autonomy_decision_logs(session=mock_db)
            
            assert isinstance(result, list)
            assert result == []

    def test_list_decision_logs_with_filters(self, mock_db):
        """필터가 포함된 의사결정 로그 조회 테스트"""
        with patch('app.api.endpoints.autonomy.select') as mock_select:
            mock_scalars = Mock()
            mock_scalars.all.return_value = []
            
            mock_select.return_value.where.return_value.order_by.return_value.limit.return_value.scalars = Mock(return_value=mock_scalars)
            
            result = list_autonomy_decision_logs(
                session=mock_db,
                decision="APPLIED",
                segment_key="test_segment",
                limit=50
            )
            
            assert isinstance(result, list)


class TestAutonomySegmentStats:
    """세그먼트별 성과 통계 API 테스트"""

    def test_get_segment_stats_returns_list(self, mock_db):
        """성과 통계 조회 테스트"""
        with patch('app.api.endpoints.autonomy.select') as mock_select:
            mock_execute = Mock()
            mock_execute.return_value.all.return_value = []
            
            mock_select.return_value.where.return_value.group_by.return_value.order_by.return_value.execute = Mock(return_value=mock_execute)
            
            result = get_segment_stats(session=mock_db)
            
            assert isinstance(result, list)

    def test_get_segment_stats_custom_days(self, mock_db):
        """사용자 지정 기간으로 통계 조회 테스트"""
        with patch('app.api.endpoints.autonomy.select') as mock_select:
            mock_execute = Mock()
            mock_execute.return_value.all.return_value = []
            
            mock_select.return_value.where.return_value.group_by.return_value.order_by.return_value.execute = Mock(return_value=mock_execute)
            
            result = get_segment_stats(session=mock_db, days=30)
            
            assert isinstance(result, list)


class TestAutonomyKillSwitch:
    """전역 킬스위치 API 테스트"""

    def test_get_processing_kill_switch_disabled(self, mock_db):
        """상품 가공 킬스위치 비활성 상태 조회 테스트"""
        with patch('app.api.endpoints.autonomy.select') as mock_select:
            mock_execute = Mock()
            mock_execute.return_value.scalars.return_value.first.return_value = None
            
            mock_select.return_value.where.return_value.execute = Mock(return_value=mock_execute)
            
            result = get_processing_kill_switch(session=mock_db)
            
            assert result.enabled is False

    def test_get_processing_kill_switch_enabled(self, mock_db):
        """상품 가공 킬스위치 활성 상태 조회 테스트"""
        setting = Mock(spec=SystemSetting)
        setting.value = {"enabled": True}
        setting.updated_at = Mock()
        
        with patch('app.api.endpoints.autonomy.select') as mock_select:
            mock_execute = Mock()
            mock_execute.return_value.scalars.return_value.first.return_value = setting
            
            mock_select.return_value.where.return_value.execute = Mock(return_value=mock_execute)
            
            result = get_processing_kill_switch(session=mock_db)
            
            assert result.enabled is True

    def test_set_processing_kill_switch_enable(self, mock_db):
        """상품 가공 킬스위치 활성화 테스트"""
        with patch('app.api.endpoints.autonomy.select') as mock_select:
            setting = Mock(spec=SystemSetting)
            mock_execute = Mock()
            mock_execute.return_value.scalars.return_value.first.return_value = None  # 설정 없음
            
            mock_select.return_value.where.return_value.execute = Mock(return_value=mock_execute)
            
            new_setting = Mock(spec=SystemSetting)
            with patch.object(mock_db, 'add', return_value=new_setting):
                with patch.object(mock_db, 'commit'):
                    result = set_processing_kill_switch(
                        session=mock_db,
                        payload=Mock(enabled=True)
                    )
                    
                    assert result.enabled is True

    def test_set_processing_kill_switch_disable(self, mock_db):
        """상품 가공 킬스위치 비활성화 테스트"""
        with patch('app.api.endpoints.autonomy.select') as mock_select:
            setting = Mock(spec=SystemSetting)
            setting.value = {"enabled": True}
            mock_execute = Mock()
            mock_execute.return_value.scalars.return_value.first.return_value = setting
            
            mock_select.return_value.where.return_value.execute = Mock(return_value=mock_execute)
            
            with patch.object(mock_db, 'commit'):
                result = set_processing_kill_switch(
                    session=mock_db,
                    payload=Mock(enabled=False)
                )
                
                assert result.enabled is False

    def test_get_pricing_kill_switch(self, mock_db):
        """가격 변경 킬스위치 조회 테스트"""
        with patch('app.api.endpoints.autonomy.select') as mock_select:
            mock_execute = Mock()
            mock_execute.return_value.scalars.return_value.first.return_value = None
            
            mock_select.return_value.where.return_value.execute = Mock(return_value=mock_execute)
            
            result = get_pricing_kill_switch(session=mock_db)
            
            assert result.enabled is False

    def test_set_pricing_kill_switch(self, mock_db):
        """가격 변경 킬스위치 설정 테스트"""
        with patch('app.api.endpoints.autonomy.select') as mock_select:
            mock_execute = Mock()
            mock_execute.return_value.scalars.return_value.first.return_value = None
            
            mock_select.return_value.where.return_value.execute = Mock(return_value=mock_execute)
            
            new_setting = Mock(spec=SystemSetting)
            with patch.object(mock_db, 'add', return_value=new_setting):
                with patch.object(mock_db, 'commit'):
                    result = set_pricing_kill_switch(
                        session=mock_db,
                        payload=Mock(enabled=True)
                    )
                    
                    assert result.enabled is True


class TestAutonomyTuner:
    """자율 정책 튜너 API 테스트"""

    def test_run_autonomy_tuner(self, mock_db):
        """튜너 실행 테스트"""
        mock_results = [
            {
                "segment": "test_segment_1",
                "action": "PROMOTION_RECOMMENDED",
                "reason": "Stable performance for 14 days"
            },
            {
                "segment": "test_segment_2",
                "action": "DEMOTE",
                "reason": "Critical rejection rate"
            }
        ]
        
        with patch('app.api.endpoints.autonomy.AutonomyTuner') as mock_tuner_class:
            mock_tuner = Mock()
            mock_tuner.return_value.run_evolution_cycle.return_value = mock_results
            
            with patch('app.api.endpoints.autonomy.AutonomyTuner', return_value=mock_tuner_class):
                result = run_autonomy_tuner(session=mock_db, days=14)
                
                assert result["analyzed_segments"] == 2
                assert result["results"] == mock_results
                assert "message" in result

    def test_run_autonomy_tuner_custom_days(self, mock_db):
        """사용자 지정 기간으로 튜너 실행 테스트"""
        with patch('app.api.endpoints.autonomy.AutonomyTuner') as mock_tuner_class:
            mock_tuner = Mock()
            mock_tuner.return_value.run_evolution_cycle.return_value = []
            
            with patch('app.api.endpoints.autonomy.AutonomyTuner', return_value=mock_tuner_class):
                result = run_autonomy_tuner(session=mock_db, days=30)
                
                assert result["analyzed_segments"] == 0
