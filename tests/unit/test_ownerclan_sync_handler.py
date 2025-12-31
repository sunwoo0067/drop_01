"""
OwnerClan 핸들러 테스트.

PR-2 Part 2의 핵심 목표 달성을 위한 단위 테스트입니다.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from sqlalchemy.orm import Session
from app.ownerclan_sync_handler import OwnerClanItemSyncHandler, OwnerClanJobResult
from app.models import SupplierSyncJob


@pytest.mark.unit
class TestOwnerClanItemSyncHandlerCalculations:
    """OwnerClanItemSyncHandler의 순수 계산 로직 테스트."""
    
    @pytest.fixture
    def mock_handler(self):
        """Mock handler fixture."""
        session = Mock(spec=Session)
        job = SupplierSyncJob(
            supplier_code="ownerclan",
            job_type="ownerclan_items_raw",
            params={}
        )
        client = Mock()
        return OwnerClanItemSyncHandler(
            session=session,
            job=job,
            client=client
        )
    
    def test_batch_commit_size_default(self, mock_handler):
        """배치 커밋 기본값(200) 확인."""
        assert mock_handler.batch_commit_size == 200
    
    def test_batch_commit_size_custom(self, mock_handler):
        """배치 커밋 사용자 정의값 확인."""
        handler = OwnerClanItemSyncHandler(
            session=mock_handler.session,
            job=mock_handler.job,
            client=mock_handler.client,
            batch_commit_size=500
        )
        assert handler.batch_commit_size == 500
    
    def test_max_pages_default(self, mock_handler):
        """최대 페이지 기본값(50) 확인."""
        assert mock_handler.max_pages == 50
    
    def test_max_pages_custom(self, mock_handler):
        """최대 페이지 사용자 정의값 확인."""
        handler = OwnerClanItemSyncHandler(
            session=mock_handler.session,
            job=mock_handler.job,
            client=mock_handler.client,
            max_pages=100
        )
        assert handler.max_pages == 100
    
    def test_max_items_per_batch_default(self, mock_handler):
        """최대 아이템 기본값(5000) 확인."""
        assert mock_handler.max_items_per_batch == 5000


@pytest.mark.unit
class TestOwnerClanItemSyncHandlerExceptionHandling:
    """OwnerClanItemSyncHandler의 예외 처리 테스트."""
    
    @pytest.fixture
    def mock_handler(self, mock_session):
        """Mock handler with session fixture."""
        job = SupplierSyncJob(
            supplier_code="ownerclan",
            job_type="ownerclan_items_raw",
            params={}
        )
        client = Mock()
        return OwnerClanItemSyncHandler(
            session=mock_session,
            job=job,
            client=client
        )
    
    @pytest.fixture
    def mock_session(self):
        """Mock session fixture (no real DB)."""
        session = MagicMock(spec=Session)
        yield session
    
    def test_sync_success(self, mock_handler, mock_session):
        """성공적인 동기화 테스트."""
        # Mock client methods: 적어도 하나의 키를 반환해야 루프가 돌아감
        mock_handler.client.graphql = Mock(return_value=(200, {
            "data": {
                "allItems": {
                    "pageInfo": {"hasNextPage": False}, 
                    "edges": [{"node": {"key": "item_1"}}]
                }
            }
        }))
        mock_handler.fetch_item_details_batch = Mock(return_value=[{"key": "item_1"}])
        # mock_handler.state["total_processed"]를 직접 업데이트하는 부수효과 추가
        def mock_save_effect(items):
            mock_handler.state["total_processed"] = 10
            return 10
        mock_handler.normalize_and_save_items = Mock(side_effect=mock_save_effect)
        mock_handler.save_state = Mock()
        
        result = mock_handler.sync()
        
        assert result.processed == 10
        assert result.error is None
    
    def test_sync_empty_keys(self, mock_handler, mock_session):
        """빈 키 목록 처리 테스트."""
        # Mock client: 빈 키 목록 반환
        mock_handler.client.graphql = Mock(return_value=(200, {"data": {"allItems": {"pageInfo": {"hasNextPage": False}, "edges": []}}}))
        mock_handler.fetch_item_details_batch = Mock(return_value=[])
        mock_handler.normalize_and_save_items = Mock(return_value=0)
        mock_handler.save_state = Mock()
        
        result = mock_handler.sync()
        
        assert result.processed == 0
        assert result.error is None
    
    def test_sync_auth_failure(self, mock_handler, mock_session):
        """인증 실패 테스트 (RuntimeError)."""
        # Mock client: 401 반환
        mock_handler.client.graphql = Mock(return_value=(401, {"errors": [{"message": "unauthorized"}]}))
        
        with pytest.raises(RuntimeError, match="인증이 만료"):
            mock_handler.fetch_item_keys_batch(
                date_from_ms=0,
                date_to_ms=10000,
                cursor=None,
                first=100
            )
    
    def test_sync_api_failure(self, mock_handler, mock_session):
        """API 실패 테스트 (429/5xx)."""
        # Mock client: 429 반환
        mock_handler.client.graphql = Mock(return_value=(429, {"errors": [{"message": "rate limit"}]}))
        
        # tenacity retry를 일시적으로 비활성화하거나 단계를 줄여서 테스트
        # 실제로는 retry가 작동하므로 RuntimeError가 최종적으로 발생함
        with pytest.raises(RuntimeError, match="GraphQL 호출 실패"):
            mock_handler.fetch_item_keys_batch(
                date_from_ms=0,
                date_to_ms=10000,
                cursor=None,
                first=100
            )


@pytest.mark.unit
class TestOwnerClanItemSyncHandlerBatchCommit:
    """배치 커밋 및 트랜잭션 관리 테스트 (PR-4)."""

    @pytest.fixture
    def mock_handler(self):
        session = MagicMock(spec=Session)
        job = SupplierSyncJob(
            supplier_code="ownerclan",
            job_type="ownerclan_items_raw",
            params={}
        )
        client = Mock()
        return OwnerClanItemSyncHandler(
            session=session,
            job=job,
            client=client,
            batch_commit_size=5  # 테스트를 위해 작게 설정
        )

    def test_normalize_and_save_items_batch_commit(self, mock_handler):
        """배치 크기에 맞춰 커밋이 발생하는지 확인."""
        items = [{"key": f"item_{i}", "id": f"id_{i}", "updatedAt": "2023-01-01T00:00:00Z"} for i in range(12)]
        
        # patch insert to avoid real DB calls
        with patch("app.ownerclan_sync_handler.insert") as mock_insert:
            mock_insert.return_value.values.return_value.on_conflict_do_update.return_value = MagicMock()
            
            processedcount = mock_handler.normalize_and_save_items(items)
            
            assert processedcount == 12
            # 12개 아이템, 배치 크기 5 -> 5개(1회), 10개(2회), 나머지 2개(3회) = 총 3회 commit
            assert mock_handler.session.commit.call_count == 3
            # progress 업데이트 확인 (마지막 총합 12)
            assert mock_handler.job.progress == 12

    def test_normalize_and_save_items_rollback_on_error(self, mock_handler):
        """오류 발생 시 롤백이 호출되는지 확인."""
        items = [{"key": "item_1", "id": "id_1", "updatedAt": "2023-01-01T00:00:00Z"}]
        
        # execute 시 예외 발생 유도
        mock_handler.session.execute.side_effect = Exception("DB Error")
        
        with pytest.raises(Exception, match="DB Error"):
            mock_handler.normalize_and_save_items(items)
            
        mock_handler.session.rollback.assert_called_once()
        # commit은 호출되지 않아야 함
        mock_handler.session.commit.assert_not_called()
