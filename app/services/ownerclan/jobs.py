from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models import SupplierSyncJob

logger = logging.getLogger(__name__)

def start_background_ownerclan_job(session_factory: Any, job_id: uuid.UUID) -> None:
    """
    OwnerClan 동기화 작업을 백그라운드 스레드에서 시작합니다.
    """
    from app.services.ownerclan.dispatcher import run_ownerclan_job
    
    def _run() -> None:
        # Job 레코드 대기 (트랜잭션 커밋 지연 대응)
        for _ in range(200):
            with session_factory() as session:
                job = session.get(SupplierSyncJob, job_id)
                if job:
                    job.status = "running"
                    job.started_at = datetime.now(timezone.utc)
                    session.commit()
                    break
            time.sleep(0.1)
        else:
            logger.error(f"Job {job_id} not found after waiting.")
            return

        try:
            with session_factory() as session:
                job = session.get(SupplierSyncJob, job_id)
                if not job:
                    return
                
                # 실제 작업 실행
                run_ownerclan_job(session, job)
                
                job.status = "succeeded"
                job.finished_at = datetime.now(timezone.utc)
                session.commit()
                
            # Sourcing Candidate 변환 트리거 (Best Effort)
            try:
                with session_factory() as session:
                    from app.services.sourcing_service import SourcingService
                    service = SourcingService(session)
                    service.import_from_raw(limit=2000)
            except Exception as cvt_e:
                logger.warning(f"Raw 데이터를 소싱 후보로 변환하는 중 오류 발생: {cvt_e}")

        except Exception as e:
            logger.exception(f"OwnerClan 백그라운드 작업 중 오류 발생 ({job_id}): {e}")
            with session_factory() as session:
                job = session.get(SupplierSyncJob, job_id)
                if job:
                    job.status = "failed"
                    job.last_error = str(e)
                    job.finished_at = datetime.now(timezone.utc)
                    session.commit()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
