"""Pytest configuration and fixtures."""

import pytest
from sqlalchemy import create_engine, JSON
from sqlalchemy.orm import sessionmaker, Session
from app.models import SourceBase, DropshipBase, MarketBase


# 테스트용 메모리 SQLite 엔진
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False  # 테스트 로그 줄이기
)

TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    expire_on_commit=False,
)


def _patch_jsonb_to_json(base):
    """
    SQLite에서 JSONB를 JSON으로 변경하여 컴파일 오류 방지.
    테스트용으로만 사용.
    """
    from sqlalchemy.dialects.postgresql import JSONB
    
    for table in base.metadata.sorted_tables:
        for column in table.columns:
            if isinstance(column.type, JSONB):
                # JSONB → JSON으로 변경 (SQLite 호환)
                column.type = JSON()


@pytest.fixture(scope="function")
def test_session() -> Session:
    """
    테스트용 데이터베이스 세션 fixture.
    각 테스트마다 새로운 메모리 DB 생성.
    """
    # JSONB → JSON 패치 (SQLite 호환)
    _patch_jsonb_to_json(SourceBase)
    _patch_jsonb_to_json(DropshipBase)
    _patch_jsonb_to_json(MarketBase)
    
    # 모든 Base 생성
    SourceBase.metadata.create_all(bind=test_engine)
    DropshipBase.metadata.create_all(bind=test_engine)
    MarketBase.metadata.create_all(bind=test_engine)

    session = TestSessionLocal()
    try:
        yield session
        session.commit()  # 테스트 성공 시 commit
    except Exception:
        session.rollback()  # 실패 시 rollback
        raise
    finally:
        session.close()
        # 모든 테이블 삭제
        MarketBase.metadata.drop_all(bind=test_engine)
        DropshipBase.metadata.drop_all(bind=test_engine)
        SourceBase.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def db_session(test_session: Session):
    """
    기존 코드 호환용 alias.
    test_session과 동일하게 동작.
    """
    yield test_session


@pytest.fixture(scope="function")
def clean_db(test_session: Session):
    """
    테스트 시작 시 DB를 깨끗한 상태로 유지하는 fixture.
    필요한 데이터만 테스트에서 주입.
    """
    yield test_session
    # 테스트 종료 후 자동 cleanup은 test_session에서 처리


# 테스트 마커 정의
def pytest_configure(config):
    """Pytest 마커 등록."""
    config.addinivalue_line("markers", "unit: 단위 테스트 (DB 불필요)")
    config.addinivalue_line("markers", "integration: 통합 테스트 (실제 DB/API 필요)")
    config.addinivalue_line("markers", "slow: 느린 테스트 (> 1분)")
