import pytest
import uuid
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.services.sync_runner import SyncRunner
from app.models import SyncRun, SyncCursor, SyncRunError

def test_sync_runner_advisory_lock():
    """Advisory Lock을 이용한 중복 실행 방지 테스트 (서로 다른 세션 사용)"""
    session1 = SessionLocal()
    session2 = SessionLocal()
    
    runner1 = SyncRunner(session1, "test_vendor", "test_channel")
    runner2 = SyncRunner(session2, "test_vendor", "test_channel")
    
    try:
        # runner1이 락을 획득
        assert runner1._acquire_lock() is True
        
        runner2.session.commit() # 명시적 인지를 위해
        assert runner2._acquire_lock() is False
        
        # runner1이 락 해제
        runner1._release_lock()
        session1.commit()
        
        # 이제 runner2가 락 획득 성공해야 함
        assert runner2._acquire_lock() is True
        runner2._release_lock()
    finally:
        session1.close()
        session2.close()

def test_sync_runner_lifecycle_and_metrics():
    """SyncRunner의 전체 실행 생명주기 및 메트릭 기록 테스트"""
    session = SessionLocal()
    unique_channel = f"chan_{uuid.uuid4().hex[:8]}"
    runner = SyncRunner(session, "test_vendor", unique_channel)
    
    def mock_success_job(sync_run: SyncRun):
        sync_run.read_count = 100
        sync_run.write_count = 80
        sync_run.error_count = 0
        sync_run.cursor_after = "NEW_CURSOR_VAL"

    # 실행
    runner.run(mock_success_job)
    
    # DB 기록 확인
    sync_run = session.query(SyncRun).filter_by(vendor="test_vendor", channel=unique_channel).first()
    assert sync_run is not None
    assert sync_run.status == "success"
    assert sync_run.write_count == 80
    assert sync_run.cursor_before is None
    
    cursor = session.query(SyncCursor).filter_by(vendor="test_vendor", channel=unique_channel).first()
    assert cursor is not None
    assert cursor.cursor == "NEW_CURSOR_VAL"
    
    # 2번째 실행 (증분 확인)
    def mock_partial_job(sync_run: SyncRun):
        sync_run.write_count = 5
        # log_error가 내부적으로 error_count를 1 증가시키므로 명시적 설정은 0으로 함
        sync_run.error_count = 0 
        runner.log_error(sync_run, "test_entity", "Something went wrong")

    runner.run(mock_partial_job)
    
    recent_run = session.query(SyncRun).filter_by(vendor="test_vendor", channel=unique_channel).order_by(SyncRun.created_at.desc()).first()
    assert recent_run.cursor_before == "NEW_CURSOR_VAL"
    assert recent_run.status == "partial"
    assert recent_run.error_count == 1
    
    error_log = session.query(SyncRunError).filter_by(run_id=recent_run.id).first()
    assert error_log.message == "Something went wrong"
    
    session.close()

if __name__ == "__main__":
    # 간단 수동 실행용
    test_sync_runner_advisory_lock()
    test_sync_runner_lifecycle_and_metrics()
    print("Integration tests passed!")
