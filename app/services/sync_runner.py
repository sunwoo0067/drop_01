import time
import uuid
import logging
import traceback
import hashlib
from datetime import datetime, timezone
from typing import Callable, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models import SyncRun, SyncRunError, SyncCursor

logger = logging.getLogger(__name__)

class SyncRunner:
    """
    공통 동기화 잡 러너.
    - Advisory Lock을 통한 중복 실행 방지
    - 실행 이력(SyncRun) 및 에러(SyncRunError) 기록
    - 증분 동기화 커서(SyncCursor) 관리
    """
    def __init__(self, session: Session, vendor: str, channel: str):
        self.session = session
        self.vendor = vendor
        self.channel = channel
        self.run_id: Optional[uuid.UUID] = None
        # 안정적인 64비트 signed 정수 락 ID 생성 (Postgres bigint 호환)
        self.lock_id = int(hashlib.md5(f"{vendor}:{channel}".encode()).hexdigest()[:16], 16)
        if self.lock_id > 0x7FFFFFFFFFFFFFFF:
            self.lock_id -= 0x10000000000000000

    def _acquire_lock(self) -> bool:
        """Postgres advisory lock을 사용하여 인스턴스/프로세스 간 중복 실행 방지"""
        try:
            # 명시적으로 SyncRun 모델이 연결된 커넥션을 사용하여 락 획득 시도
            from sqlalchemy.orm import class_mapper
            conn = self.session.connection(bind_arguments={"mapper": class_mapper(SyncRun)})
            result = conn.execute(
                text("SELECT pg_try_advisory_lock(:id)"), 
                {"id": self.lock_id}
            ).scalar()
            return bool(result)
        except Exception as e:
            logger.error(f"[SYNC] Failed to acquire lock for {self.vendor}:{self.channel}: {e}")
            return False

    def _release_lock(self):
        """Advisory lock 해제"""
        try:
            from sqlalchemy.orm import class_mapper
            conn = self.session.connection(bind_arguments={"mapper": class_mapper(SyncRun)})
            conn.execute(
                text("SELECT pg_advisory_unlock(:id)"), 
                {"id": self.lock_id}
            )
        except Exception as e:
            logger.error(f"[SYNC] Failed to release lock for {self.vendor}:{self.channel}: {e}")

    def run(self, func: Callable[[SyncRun], Any], **kwargs):
        """
        동기화 작업을 감싸서 실행합니다.
        
        Args:
            func: 실제 동기화 로직을 담은 함수. SyncRun 객체를 인자로 받습니다.
            **kwargs: meta 정보를 포함할 수 있습니다.
        """
        if not self._acquire_lock():
            logger.warning(f"[SYNC] {self.vendor}:{self.channel} is already running. Skipping this run.")
            return

        # 1. 이전 커서 조회
        cursor_record = self.session.query(SyncCursor).filter_by(
            vendor=self.vendor, 
            channel=self.channel
        ).first()
        cursor_before = cursor_record.cursor if cursor_record else None

        # 2. SyncRun 기록 시작
        sync_run = SyncRun(
            vendor=self.vendor,
            channel=self.channel,
            status="running",
            cursor_before=cursor_before,
            meta=kwargs.get("meta", {})
        )
        self.session.add(sync_run)
        self.session.commit() # ID 생성을 위해 커밋
        self.run_id = sync_run.id

        start_time = time.time()
        logger.info(f"[SYNC] Starting run {self.run_id} ({self.vendor}:{self.channel})")

        try:
            # 3. 로직 실행
            func(sync_run)
            
            # 오류 건수가 있으면 partial, 없으면 success
            if sync_run.status == "running": # 내부에서 변경하지 않은 경우만
                sync_run.status = "success" if sync_run.error_count == 0 else "partial"
                
        except Exception as e:
            logger.error(f"[SYNC] Run {self.run_id} encountered a critical failure: {e}")
            sync_run.status = "fail"
            self.log_error(sync_run, "system", str(e), traceback.format_exc())
            # 상위로 예외를 다시 던지지 않고 로그만 남길지 결정 가능 (여기서는 기록 후 상황에 따라)
            # raise # 필요 시 주석 해제

        finally:
            end_time = time.time()
            sync_run.finished_at = datetime.now(timezone.utc)
            sync_run.duration_ms = int((end_time - start_time) * 1000)
            
            # 4. 커서 업데이트
            if sync_run.cursor_after:
                if not cursor_record:
                    cursor_record = SyncCursor(vendor=self.vendor, channel=self.channel)
                    self.session.add(cursor_record)
                cursor_record.cursor = sync_run.cursor_after
            
            self.session.commit()
            self._release_lock()
            logger.info(f"[SYNC] Run {self.run_id} completed. Status: {sync_run.status}, Processed: {sync_run.write_count}, Errors: {sync_run.error_count}")

    def log_error(self, sync_run: SyncRun, entity_type: str, message: str, 
                  stack: Optional[str] = None, entity_id: Optional[str] = None, raw: Optional[dict] = None):
        """상세 에러 기록 보조 메서드"""
        error_entry = SyncRunError(
            run_id=sync_run.id,
            entity_type=entity_type,
            entity_id=entity_id,
            message=message,
            stack=stack,
            raw=raw
        )
        self.session.add(error_entry)
        sync_run.error_count += 1
