from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.models import MarketAccount, QnaThread, QnaMessage, SyncRun
from app.services.sync_runner import SyncRunner
from app.coupang_client import CoupangClient

logger = logging.getLogger(__name__)

class CoupangQnaSync:
    """
    쿠팡 고객 문의(QnA) 동기화 서비스.
    """
    def __init__(self, session: Session, account: MarketAccount):
        self.session = session
        self.account = account
        self.client = self._get_client(account)
        self.runner = SyncRunner(session, vendor="coupang", channel=f"qna:{account.name}")

    def _get_client(self, account: MarketAccount) -> CoupangClient:
        creds = account.credentials
        return CoupangClient(
            access_key=creds.get("access_key"),
            secret_key=creds.get("secret_key"),
            vendor_id=creds.get("vendor_id")
        )

    def run(self):
        self.runner.run(self._sync_logic, meta={"account_id": str(self.account.id)})

    def _sync_logic(self, sync_run: SyncRun):
        # 1. 동기화 구간 결정 (yyyy-MM-dd)
        now = datetime.now(timezone.utc)
        if sync_run.cursor_before:
            try:
                # ISO 문자열 파싱 시도
                base_time = datetime.fromisoformat(sync_run.cursor_before)
                # 안정성을 위해 1일의 Overlap Window 적용 (단위가 기므로)
                start_time = base_time - timedelta(days=1)
            except ValueError:
                start_time = now - timedelta(days=7) # 쿠팡 최대 7일
        else:
            start_time = now - timedelta(days=7)
            
        str_from = start_time.strftime("%Y-%m-%d")
        str_to = now.strftime("%Y-%m-%d")
        
        page_num = 1
        total_processed = 0
        
        logger.info(f"[SYNC:QNA] Starting Coupang QnA sync for '{self.account.name}' from {str_from} to {str_to}")
        
        while True:
            # 최근 문의 목록 조회
            code, data = self.client.get_customer_inquiries(
                inquiry_start_at=str_from,
                inquiry_end_at=str_to,
                pageSize=50,
                pageNum=page_num
            )
            sync_run.api_calls += 1
            
            if code >= 400:
                logger.error(f"[SYNC:QNA] Failed to fetch QnA for {self.account.name}: {data}")
                self.runner.log_error(sync_run, "api", f"QnA fetch failed (HTTP {code})", raw=data)
                break
                
            inquiries = data.get("data", [])
            if not inquiries:
                break
                
            for raw in inquiries:
                try:
                    self._process_qna(sync_run, raw)
                    total_processed += 1
                except Exception as e:
                    logger.exception(f"Qna processing failed: {raw.get('inquiryId')}")
                    self.runner.log_error(
                        sync_run, "qna_processing", str(e), 
                        entity_id=str(raw.get("inquiryId")), 
                        raw=raw
                    )
            
            # 페이지네이션 (쿠팡 QnA는 pageNum 방식)
            if len(inquiries) < 50:
                break
            page_num += 1
        
        sync_run.write_count = total_processed
        sync_run.cursor_after = now.isoformat()
        logger.info(f"[SYNC:QNA] Finished Coupang QnA sync for '{self.account.name}'. Processed: {total_processed}")

    def _process_qna(self, sync_run: SyncRun, raw: dict[str, Any]):
        vendor_thread_id = str(raw.get("inquiryId"))
        
        # 1. Thread Upsert (헤더 정보)
        # 답변 여부에 따른 내부 상태 매핑
        is_answered = raw.get("answered", False)
        status = "ANSWERED" if is_answered else "OPEN"
        
        stmt = insert(QnaThread).values(
            vendor="COUPANG",
            vendor_thread_id=vendor_thread_id,
            status=status,
            title=f"QnA at {raw.get('inquiryAt')}",
            raw=raw
        ).on_conflict_do_update(
            index_elements=["vendor_thread_id"],
            set_={
                "status": status,
                "raw": raw,
                "updated_at": datetime.now(timezone.utc)
            }
        ).returning(QnaThread.id)
        
        thread_uuid = self.session.execute(stmt).scalar()
        
        # 2. Messages (질문 및 답변 분리 저장)
        # 질문 (IN)
        question_id = f"CP_Q_{vendor_thread_id}"
        stmt_q = insert(QnaMessage).values(
            thread_id=thread_uuid,
            vendor_message_id=question_id,
            direction="IN",
            body=raw.get("content", ""),
            raw=raw
        ).on_conflict_do_update(
            index_elements=["vendor_message_id"],
            set_={"body": raw.get("content", ""), "raw": raw}
        )
        self.session.execute(stmt_q)
        
        # 답변 (OUT) - 답변이 있는 경우만 처리
        if is_answered and raw.get("answer"):
            answer_data = raw.get("answer")
            answer_id = f"CP_A_{vendor_thread_id}"
            stmt_a = insert(QnaMessage).values(
                thread_id=thread_uuid,
                vendor_message_id=answer_id,
                direction="OUT",
                body=answer_data.get("answerText", ""),
                raw=answer_data
            ).on_conflict_do_update(
                index_elements=["vendor_message_id"],
                set_={"body": answer_data.get("answerText", ""), "raw": answer_data}
            )
            self.session.execute(stmt_a)
