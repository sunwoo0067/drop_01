from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.models import MarketAccount, QnaThread, QnaMessage, SyncRun
from app.services.sync_runner import SyncRunner
from app.smartstore_client import SmartStoreClient

logger = logging.getLogger(__name__)

class NaverQnaSync:
    """
    네이버 스마트스토어 고객 문의(QnA) 동기화 서비스.
    """
    def __init__(self, session: Session, account: MarketAccount):
        self.session = session
        self.account = account
        self.client = self._get_client(account)
        self.runner = SyncRunner(session, vendor="naver", channel=f"qna:{account.name}")

    def _get_client(self, account: MarketAccount) -> SmartStoreClient:
        creds = account.credentials
        return SmartStoreClient(
            client_id=creds.get("client_id"),
            client_secret=creds.get("client_secret")
        )

    def run(self):
        self.runner.run(self._sync_logic, meta={"account_id": str(self.account.id)})

    def _sync_logic(self, sync_run: SyncRun):
        # 1. 동기화 구간 결정 (ISO 8601: yyyy-MM-ddTHH:mm:ss)
        now = datetime.now(timezone.utc)
        if sync_run.cursor_before:
            try:
                base_time = datetime.fromisoformat(sync_run.cursor_before)
                # 안정성을 위해 1일의 Overlap Window (네이버 일시 단위 조회 특성상)
                start_time = base_time - timedelta(days=1)
            except ValueError:
                start_time = now - timedelta(days=7) # 네이버 최대 7일 조회 권장
        else:
            start_time = now - timedelta(days=7)
            
        # 네이버 API 포맷: yyyy-MM-ddTHH:mm:ss (Z 미포함이나 ISO 파싱 가능성 고려)
        fmt = "%Y-%m-%dT%H:%M:%S"
        str_from = start_time.strftime(fmt)
        str_to = now.strftime(fmt)
        
        logger.info(f"[SYNC:NAVER] Starting QnA sync for '{self.account.name}' from {str_from} to {str_to}")
        
        page = 1
        total_count = 0
        
        while True:
            data = self.client.get_customer_inquiries(
                start_datetime=str_from,
                end_datetime=str_to,
                page=page,
                size=50
            )
            sync_run.api_calls += 1
            
            contents = data.get("contents", [])
            if not contents:
                break
                
            for inquiry in contents:
                try:
                    self._process_qna(sync_run, inquiry)
                    total_count += 1
                except Exception as e:
                    logger.exception(f"Failed to process Naver QnA {inquiry.get('inquiryId')}")
                    self.runner.log_error(
                        sync_run, "qna_processing", str(e),
                        entity_id=str(inquiry.get("inquiryId")),
                        raw=inquiry
                    )
            
            # 페이지네이션
            if len(contents) < 50:
                break
            page += 1
            
        logger.info(f"[SYNC:NAVER] Finished QnA sync for '{self.account.name}'. Total processed: {total_count}")
        sync_run.cursor_after = now.isoformat()

    def _process_qna(self, sync_run: SyncRun, inquiry: dict[str, Any]):
        vendor_thread_id = str(inquiry.get("inquiryId"))
        
        # 1. Thread Upsert
        is_answered = inquiry.get("isAnswered", False)
        status = "ANSWERED" if is_answered else "OPEN"
        
        stmt = insert(QnaThread).values(
            vendor="NAVER",
            vendor_thread_id=vendor_thread_id,
            status=status,
            title=inquiry.get("inquiryType", "General Inquiry"),
            raw=inquiry
        ).on_conflict_do_update(
            index_elements=["vendor_thread_id"],
            set_={
                "status": status,
                "raw": inquiry,
                "updated_at": datetime.now(timezone.utc)
            }
        ).returning(QnaThread.id)
        
        thread_uuid = self.session.execute(stmt).scalar()
        
        # 2. Messages
        # 질문 (IN)
        question_id = f"NV_Q_{vendor_thread_id}"
        stmt_q = insert(QnaMessage).values(
            thread_id=thread_uuid,
            vendor_message_id=question_id,
            direction="IN",
            body=inquiry.get("content", ""),
            raw=inquiry
        ).on_conflict_do_update(
            index_elements=["vendor_message_id"],
            set_={"body": inquiry.get("content", ""), "raw": inquiry}
        )
        self.session.execute(stmt_q)
        
        # 답변 (OUT) - 답변이 있는 경우
        # 네이버 API 결과에 answer 객체가 있다고 가정 (또는 답변 등록 내역)
        # 실제로는 inquiry 상세 조회 API가 별도로 필요할 수도 있으나, 
        # 목록 결과에 답변이 포함되어 있다면 바로 처리.
        answer = inquiry.get("answer") or inquiry.get("repliedContent")
        if is_answered and answer:
            answer_id = f"NV_A_{vendor_thread_id}"
            body = ""
            if isinstance(answer, dict):
                body = answer.get("commentContent") or answer.get("content") or ""
            else:
                body = str(answer) # 텍스트인 경우

            stmt_a = insert(QnaMessage).values(
                thread_id=thread_uuid,
                vendor_message_id=answer_id,
                direction="OUT",
                body=body,
                raw=answer if isinstance(answer, dict) else {"content": answer}
            ).on_conflict_do_update(
                index_elements=["vendor_message_id"],
                set_={"body": body, "raw": answer if isinstance(answer, dict) else {"content": answer}}
            )
            self.session.execute(stmt_a)
