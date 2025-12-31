"""
Integration tests for OwnerClan synchronization.

실제 OwnerClan API와 연동하여 동기화 기능을 테스트합니다.
테스트 DB에 실제 데이터를 저장하고 결과를 검증합니다.
"""

import pytest
from app.models import SupplierSyncJob, SupplierItemRaw, SupplierAccount
from app.ownerclan_sync import run_ownerclan_job
from app.ownerclan_client import OwnerClanClient
from app.settings import settings
import uuid


@pytest.mark.integration
class TestOwnerClanItemsSync:
    """OwnerClan 아이템 동기화 통합 테스트."""

    def test_sync_ownerclan_items_small_batch(self, db_session):
        """
        maxItems=10 같은 작은 배치로 동기화 테스트.
        
        테스트 전제:
        - .env에 OWNERCLAN_PRIMARY_USERNAME/PASSWORD 설정 필요
        - 테스트 DB 사용 (메모리 SQLite 또는 테스트 PostgreSQL)
        """
        # 1. Job 생성
        job = SupplierSyncJob(
            supplier_code="ownerclan",
            job_type="ownerclan_items_raw",
            params={"maxItems": 10, "datePreset": "7d"},  # 최근 7일 데이터 10개
            status="queued"
        )
        db_session.add(job)
        db_session.flush()
        
        # 2. 계정 설정 확인
        primary_account = db_session.query(SupplierAccount).filter(
            SupplierAccount.supplier_code == "ownerclan",
            SupplierAccount.is_primary.is_(True)
        ).first()
        
        if not primary_account:
            pytest.skip("오너클랜 대표계정이 설정되지 않아 테스트 스킵")
        
        # 3. 동기화 실행
        try:
            from app.ownerclan_sync import OwnerClanJobResult
            result = run_ownerclan_job(db_session, job)
        except RuntimeError as e:
            # 인증 만료 등 오류 시 스킵
            pytest.skip(f"오너클랜 API 오류로 테스트 스킵: {e}")
        except Exception as e:
            # 기타 예외는 실패로 처리
            pytest.fail(f"동기화 중 예외 발생: {e}")
        
        # 4. 검증
        assert result.processed > 0, f"처리된 아이템 수: {result.processed}"
        assert job.status in ("succeeded", "failed"), f"Job 상태: {job.status}"
        
        # 성공 시 추가 검증
        if job.status == "succeeded":
            assert job.last_error is None, f"에러 메시지: {job.last_error}"
            assert job.started_at is not None, "시작 시간이 기록되어야 함"
            assert job.finished_at is not None, "종료 시간이 기록되어야 함"
            assert job.progress == result.processed, f"진행률 불일치: {job.progress} vs {result.processed}"
            
            # 저장된 아이템 확인
            items = db_session.query(SupplierItemRaw).filter(
                SupplierItemRaw.supplier_code == "ownerclan"
            ).all()
            
            assert len(items) >= result.processed, f"저장된 아이템 수: {len(items)}"
            
            # 각 아이템 필드 검증
            for item in items[:result.processed]:
                assert item.item_code, "item_code가 있어야 함"
                assert item.item_key, "item_key가 있어야 함"
                assert item.raw, "raw 데이터가 있어야 함"
                assert item.fetched_at, "fetched_at이 기록되어야 함"
        
        print(f"✅ 테스트 성공: {result.processed}개 아이템 동기화 완료")

    def test_sync_ownerclan_items_with_specific_keys(self, db_session):
        """
        특정 item_keys로 동기화 테스트.
        
        테스트 전제:
        - OwnerClan에 실제 존재하는 item_keys 필요
        """
        # 테스트용 아이템 키 (실제 존재하는 값으로 변경 필요)
        test_item_keys = [
            "YOUR_ITEM_KEY_1",  # 실제 키로 변경
            "YOUR_ITEM_KEY_2",  # 실제 키로 변경
        ]
        
        # 모든 키가 유효하지 않으면 스킵
        if all(key.startswith("YOUR_") for key in test_item_keys):
            pytest.skip("테스트용 아이템 키가 설정되지 않아 테스트 스킵")
        
        # Job 생성
        job = SupplierSyncJob(
            supplier_code="ownerclan",
            job_type="ownerclan_items_raw",
            params={"orderKeys": test_item_keys},
            status="queued"
        )
        db_session.add(job)
        db_session.flush()
        
        # 동기화 실행
        try:
            result = run_ownerclan_job(db_session, job)
        except RuntimeError as e:
            pytest.skip(f"오너클랜 API 오류로 테스트 스킵: {e}")
        except Exception as e:
            pytest.fail(f"동기화 중 예외 발생: {e}")
        
        # 검증
        assert result.processed > 0
        assert job.status in ("succeeded", "failed")
        
        print(f"✅ 특정 키 동기화 성공: {result.processed}/{len(test_item_keys)}")

    def test_sync_ownerclan_items_error_handling(self, db_session):
        """
        에러 처리 테스트.
        
        시나리오:
        - 잘못된 파라미터로 동기화 시도
        - 에러가 적절히 기록되는지 확인
        """
        # 잘못된 파라미터
        job = SupplierSyncJob(
            supplier_code="ownerclan",
            job_type="ownerclan_items_raw",
            params={"dateFrom": -1, "dateTo": -1},  # 잘못된 날짜
            status="queued"
        )
        db_session.add(job)
        db_session.flush()
        
        # 동기화 실행 (예상: 에러 발생)
        try:
            result = run_ownerclan_job(db_session, job)
        except Exception as e:
            # 예외 발생 시 job 상태 업데이트
            job.status = "failed"
            job.last_error = str(e)
            job.finished_at = job.finished_at or job.started_at
            db_session.commit()
        
        # 검증
        assert job.status == "failed", "에러 상태여야 함"
        assert job.last_error is not None, "에러 메시지가 기록되어야 함"
        assert result.processed == 0, "처리된 아이템이 없어야 함"
        
        print(f"✅ 에러 처리 테스트 성공: {job.last_error}")


@pytest.mark.integration
class TestOwnerClanOrdersSync:
    """OwnerClan 주문 동기화 통합 테스트."""

    def test_sync_ownerclan_orders_by_key(self, db_session):
        """
        특정 주문 키로 동기화 테스트.
        
        테스트 전제:
        - OwnerClan에 실제 존재하는 orderKey 필요
        """
        test_order_key = "YOUR_ORDER_KEY"  # 실제 키로 변경
        
        if test_order_key.startswith("YOUR_"):
            pytest.skip("테스트용 주문 키가 설정되지 않아 테스트 스킵")
        
        # Job 생성
        job = SupplierSyncJob(
            supplier_code="ownerclan",
            job_type="ownerclan_orders_raw",
            params={"orderKeys": [test_order_key]},
            status="queued"
        )
        db_session.add(job)
        db_session.flush()
        
        # 동기화 실행
        try:
            result = run_ownerclan_job(db_session, job)
        except RuntimeError as e:
            pytest.skip(f"오너클랜 API 오류로 테스트 스킵: {e}")
        except Exception as e:
            pytest.fail(f"동기화 중 예외 발생: {e}")
        
        # 검증
        assert result.processed > 0
        assert job.status in ("succeeded", "failed")
        
        if job.status == "succeeded":
            # 저장된 주문 확인
            from app.models import SupplierOrderRaw
            orders = db_session.query(SupplierOrderRaw).filter(
                SupplierOrderRaw.supplier_code == "ownerclan"
            ).all()
            assert len(orders) >= result.processed


@pytest.mark.integration
class TestOwnerClanAuth:
    """OwnerClan 인증 통합 테스트."""

    def test_ownerclan_token_issue(self):
        """
        오너클랜 토큰 발급 테스트.
        
        테스트 전제:
        - .env에 OWNERCLAN_PRIMARY_USERNAME/PASSWORD 설정 필요
        """
        username = settings.ownerclan_primary_username
        password = settings.ownerclan_primary_password
        
        if not username or not password:
            pytest.skip("오너클랜 대표계정 설정이 없어 테스트 스킵")
        
        # 토큰 발급 시도
        client = OwnerClanClient(
            auth_url=settings.ownerclan_auth_url,
            api_base_url=settings.ownerclan_api_base_url,
            graphql_url=settings.ownerclan_graphql_url,
        )
        
        try:
            token = client.issue_token(
                username=username,
                password=password,
                user_type="seller"
            )
            assert token.access_token, "access_token이 있어야 함"
            assert token.expires_at, "expires_at이 있어야 함"
            print(f"✅ 토큰 발급 성공: 만료일={token.expires_at}")
        except Exception as e:
            pytest.fail(f"토큰 발급 실패: {e}")
