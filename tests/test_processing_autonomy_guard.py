"""
ProcessingAutonomyGuard 단위 테스트

상품 가공 자율성 체크 시스템을 테스트합니다.
"""
import pytest
from unittest.mock import Mock, patch
from uuid import uuid4
from sqlalchemy.orm import Session

from app.services.processing.processing_autonomy_guard import (
    ProcessingAutonomyGuard,
    ProcessingDecisionEvent,
)
from app.models import Product


@pytest.fixture
def mock_db():
    """모의 DB 세션"""
    return Mock(spec=Session)


@pytest.fixture
def mock_product():
    """테스트용 모의 상품"""
    product = Mock(spec=Product)
    product.id = uuid4()
    product.name = "테스트 상품"
    product.brand = "테스트 브랜드"
    product.description = "테스트 설명"
    product.processed_name = None
    product.processed_image_urls = None
    product.supplier_item_id = None
    product.benchmark_product_id = None
    product.strategy_id = None
    product.lifecycle_stage = "STEP_1"
    return product


@pytest.fixture
def mock_tier0_policy():
    """Tier 0 (수동) 정책 모의"""
    policy = Mock()
    policy.tier = 0
    policy.status = "ACTIVE"
    return policy


@pytest.fixture
def mock_tier1_policy():
    """Tier 1 (Enforce Lite) 정책 모의"""
    policy = Mock()
    policy.tier = 1
    policy.status = "ACTIVE"
    return policy


@pytest.fixture
def mock_tier2_policy():
    """Tier 2 (High-Confidence) 정책 모의"""
    policy = Mock()
    policy.tier = 2
    policy.status = "ACTIVE"
    return policy


@pytest.fixture
def mock_tier3_policy():
    """Tier 3 (Full Auto) 정책 모의"""
    policy = Mock()
    policy.tier = 3
    policy.status = "ACTIVE"
    return policy


@pytest.fixture
def mock_frozen_policy():
    """동결(FROZEN) 정책 모의"""
    policy = Mock()
    policy.tier = 2
    policy.status = "FROZEN"
    return policy


class TestProcessingAutonomyGuard:
    """ProcessingAutonomyGuard 단위 테스트"""

    def test_init_creates_guard_with_db(self, mock_db):
        """초기화 시 DB 세션 설정 테스트"""
        with patch('app.services.processing.processing_autonomy_guard.SegmentResolver'):
            guard = ProcessingAutonomyGuard(mock_db)

            assert guard.db == mock_db
            assert guard.resolver is not None

    def test_check_processing_autonomy_tier0_rejects_all(self, mock_db, mock_product, mock_tier0_policy):
        """Tier 0 (수동) - 모든 가공 거절 테스트"""
        with patch('app.services.processing.processing_autonomy_guard.SegmentResolver') as mock_resolver:
            mock_resolver.return_value.get_segment_key.return_value = "test_segment"
            guard = ProcessingAutonomyGuard(mock_db)
            mock_result = Mock()
            mock_result.scalars.return_value.first.return_value = mock_tier0_policy

            with patch.object(guard, '_is_global_kill_switch_on', return_value=False):
                with patch.object(mock_db, 'execute', return_value=mock_result):
                    can_apply, reasons, tier = guard.check_processing_autonomy(
                        product=mock_product,
                        processing_type="NAME",
                        metadata={"vendor": "ownerclan", "channel": "COUPANG"}
                    )

                    assert can_apply is False
                    assert tier == 0
                    assert any("수동 승인 필수" in reason for reason in reasons)

    def test_check_processing_autonomy_tier1_allows_low_risk(self, mock_db, mock_product, mock_tier1_policy):
        """Tier 1 (Enforce Lite) - 저위험 가공 허용 테스트"""
        with patch('app.services.processing.processing_autonomy_guard.SegmentResolver') as mock_resolver:
            mock_resolver.return_value.get_segment_key.return_value = "test_segment"
            guard = ProcessingAutonomyGuard(mock_db)
            mock_result = Mock()
            mock_result.scalars.return_value.first.return_value = mock_tier1_policy

            with patch.object(guard, '_is_global_kill_switch_on', return_value=False):
                with patch.object(mock_db, 'execute', return_value=mock_result):
                    # NAME (우선순위 1) - 허용
                    can_apply, reasons, tier = guard.check_processing_autonomy(
                        product=mock_product,
                        processing_type="NAME",
                        metadata={"vendor": "ownerclan", "channel": "COUPANG"}
                    )

                    assert can_apply is True
                    assert tier == 1
                    assert any("저위험 가공" in reason for reason in reasons)

                    # IMAGE (우선순위 2) - 거절
                    can_apply2, reasons2, tier2 = guard.check_processing_autonomy(
                        product=mock_product,
                        processing_type="IMAGE",
                        metadata={"vendor": "ownerclan", "channel": "COUPANG"}
                    )

                    assert can_apply2 is False
                    assert tier2 == 1
                    assert any("고위험 가공" in reason for reason in reasons2)

    def test_check_processing_autonomy_tier2_allows_high_stage(self, mock_db, mock_tier2_policy):
        """Tier 2 (High-Confidence) - STEP_2 이상 상품 고위험 가공 허용 테스트"""
        with patch('app.services.processing.processing_autonomy_guard.SegmentResolver') as mock_resolver:
            mock_resolver.return_value.get_segment_key.return_value = "test_segment"
            guard = ProcessingAutonomyGuard(mock_db)
            mock_result = Mock()
            mock_result.scalars.return_value.first.return_value = mock_tier2_policy

            # STEP_2 상품
            high_stage_product = Mock(spec=Product)
            high_stage_product.lifecycle_stage = "STEP_2"

            with patch.object(guard, '_is_global_kill_switch_on', return_value=False):
                with patch.object(mock_db, 'execute', return_value=mock_result):
                    # PREMIUM_IMAGE (우선순위 3) - STEP_2 상품이므로 허용
                    can_apply, reasons, tier = guard.check_processing_autonomy(
                        product=high_stage_product,
                        processing_type="PREMIUM_IMAGE",
                        metadata={"vendor": "ownerclan", "channel": "COUPANG"}
                    )

                    assert can_apply is True
                    assert tier == 2
                    assert any("승격 상품" in reason for reason in reasons)

    def test_check_processing_autonomy_tier3_allows_all(self, mock_db, mock_product, mock_tier3_policy):
        """Tier 3 (Full Auto) - 모든 가공 허용 테스트"""
        with patch('app.services.processing.processing_autonomy_guard.SegmentResolver') as mock_resolver:
            mock_resolver.return_value.get_segment_key.return_value = "test_segment"
            guard = ProcessingAutonomyGuard(mock_db)
            mock_result = Mock()
            mock_result.scalars.return_value.first.return_value = mock_tier3_policy

            with patch.object(guard, '_is_global_kill_switch_on', return_value=False):
                with patch.object(mock_db, 'execute', return_value=mock_result):
                    # PREMIUM_IMAGE (우선순위 3) - 허용
                    can_apply, reasons, tier = guard.check_processing_autonomy(
                        product=mock_product,
                        processing_type="PREMIUM_IMAGE",
                        metadata={"vendor": "ownerclan", "channel": "COUPANG"}
                    )

                    assert can_apply is True
                    assert tier == 3
                    assert any("완전 자율" in reason for reason in reasons)

    def test_check_processing_autonomy_frozen_policy_rejects_all(self, mock_db, mock_product, mock_frozen_policy):
        """동결(FROZEN) 정책 - 모든 가공 거절 테스트"""
        with patch('app.services.processing.processing_autonomy_guard.SegmentResolver') as mock_resolver:
            mock_resolver.return_value.get_segment_key.return_value = "test_segment"
            guard = ProcessingAutonomyGuard(mock_db)
            mock_result = Mock()
            mock_result.scalars.return_value.first.return_value = mock_frozen_policy

            with patch.object(guard, '_is_global_kill_switch_on', return_value=False):
                with patch.object(mock_db, 'execute', return_value=mock_result):
                    can_apply, reasons, tier = guard.check_processing_autonomy(
                        product=mock_product,
                        processing_type="NAME",
                        metadata={"vendor": "ownerclan", "channel": "COUPANG"}
                    )

                    assert can_apply is False
                    assert tier == 0
                    assert any("동결 상태" in reason for reason in reasons)

    def test_check_processing_autonomy_no_policy_rejects_all(self, mock_db, mock_product):
        """정책 없음 - 모든 가공 거절 (Tier 0 기본) 테스트"""
        with patch('app.services.processing.processing_autonomy_guard.SegmentResolver') as mock_resolver:
            mock_resolver.return_value.get_segment_key.return_value = "test_segment"
            guard = ProcessingAutonomyGuard(mock_db)
            mock_result = Mock()
            mock_result.scalars.return_value.first.return_value = None

            with patch.object(guard, '_is_global_kill_switch_on', return_value=False):
                with patch.object(mock_db, 'execute', return_value=mock_result):
                    can_apply, reasons, tier = guard.check_processing_autonomy(
                        product=mock_product,
                        processing_type="NAME",
                        metadata={"vendor": "ownerclan", "channel": "COUPANG"}
                    )

                    assert can_apply is False
                    assert tier == 0
                    assert any("자율성 정책 없음" in reason for reason in reasons)

    def test_check_processing_autonomy_global_kill_switch_rejects_all(self, mock_db, mock_product):
        """전역 킬스위치 활성 - 모든 가공 거절 테스트"""
        with patch('app.services.processing.processing_autonomy_guard.SegmentResolver'):
            guard = ProcessingAutonomyGuard(mock_db)
            with patch.object(guard, '_is_global_kill_switch_on', return_value=True):
                can_apply, reasons, tier = guard.check_processing_autonomy(
                    product=mock_product,
                    processing_type="NAME",
                    metadata={"vendor": "ownerclan", "channel": "COUPANG"}
                )

                assert can_apply is False
                assert tier == 0
                assert any("전역 킬스위치 활성화" in reason for reason in reasons)

    def test_check_processing_autonomy_exception_returns_false(self, mock_db, mock_product):
        """예외 발생 시 안전하게 False 반환 테스트"""
        with patch('app.services.processing.processing_autonomy_guard.SegmentResolver'):
            guard = ProcessingAutonomyGuard(mock_db)
            with patch.object(guard, '_is_global_kill_switch_on', return_value=False):
                with patch.object(mock_db, 'execute', side_effect=Exception("DB 에러")):
                    can_apply, reasons, tier = guard.check_processing_autonomy(
                        product=mock_product,
                        processing_type="NAME",
                        metadata={"vendor": "ownerclan", "channel": "COUPANG"}
                    )

                    # 예외 발생 시 안전하게 False 반환
                    assert can_apply is False
                    assert tier == 0
                    assert any("시스템 오류" in reason for reason in reasons)


class TestProcessingPriority:
    """가공 타입 우선순위 상수 테스트"""

    def test_processing_priority_constants(self):
        """가공 타입별 우선순위 상수 검증 테스트"""
        priorities = ProcessingAutonomyGuard.PROCESSING_PRIORITY
        assert priorities["NAME"] == 1
        assert priorities["KEYWORDS"] == 1
        assert priorities["DESCRIPTION"] == 2
        assert priorities["IMAGE"] == 2
        assert priorities["PREMIUM_IMAGE"] == 3
        assert priorities["FULL_BRANDING"] == 3

        # 모든 키는 1-3 사이여야 함
        for key, priority in priorities.items():
            assert priority in [1, 2, 3]


class TestProcessingDecisionEvent:
    """ProcessingDecisionEvent 클래스 테스트"""

    def test_processing_decision_event_creation(self):
        """의사결정 이벤트 생성 테스트"""
        product_id = str(uuid4())
        event = ProcessingDecisionEvent(
            product_id=product_id,
            processing_type="NAME",
            decision="APPLIED",
            tier=1,
            reasons=["저위험 가공 자동 승인"],
            metadata={"test": "data"}
        )

        assert event.product_id == product_id
        assert event.processing_type == "NAME"
        assert event.decision == "APPLIED"
        assert event.tier == 1
        assert event.reasons == ["저위험 가공 자동 승인"]
        assert event.metadata == {"test": "data"}

    def test_processing_decision_event_optional_params(self):
        """선택적 파라미터 기본값 테스트"""
        event = ProcessingDecisionEvent(
            product_id=str(uuid4()),
            processing_type="PREMIUM_IMAGE",
            decision="PENDING",
            tier=2,
            reasons=[]
        )

        assert event.metadata == {}
        assert event.reasons == []
