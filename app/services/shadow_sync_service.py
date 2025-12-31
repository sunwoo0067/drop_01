import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import MarketAccount, MarketInquiryRaw
from app.coupang_client import CoupangClient
from app.smartstore_client import SmartStoreClient
from app.services.customer_service import CustomerService

logger = logging.getLogger(__name__)

class ShadowSyncService:
    def __init__(self, session: Session):
        self.session = session
        self.cs_service = CustomerService()

    async def sync_all_markets(self) -> Dict[str, int]:
        """
        활성 계정에서 실시간 문의를 수집하고 Shadow Mode 처리를 트리거합니다.
        AI는 답변을 생성하지만 마켓으로 전송하지는 않습니다.
        """
        stmt = select(MarketAccount).where(MarketAccount.is_active == True)
        accounts = self.session.execute(stmt).scalars().all()
        
        counts = {"COUPANG": 0, "SMARTSTORE": 0}
        for account in accounts:
            try:
                if account.market_code == "COUPANG":
                    counts["COUPANG"] += await self._sync_coupang(account)
                elif account.market_code == "SMARTSTORE":
                    counts["SMARTSTORE"] += await self._sync_smartstore(account)
            except Exception as e:
                logger.error(f"Failed to sync shadow inquiries for {account.name}: {e}")
        
        logger.info(f"Shadow Sync Finished. Ingested total: {sum(counts.values())}")
        
        # 수집된 문의들에 대해 AI 처리 프로세스 트리거 (항상 HUMAN_REVIEW 또는 AI_DRAFTED 상태로 기록됨)
        # CustomerService는 마켓 전송 로직이 없으므로 Shadow Mode로 적합함.
        if sum(counts.values()) > 0:
            logger.info("Triggering AI processing for ingested inquiries...")
            await self.cs_service.generate_replies_for_unanswered_inquiries(self.session, market_code="COUPANG")
            await self.cs_service.generate_replies_for_unanswered_inquiries(self.session, market_code="SMARTSTORE")
        
        return counts

    async def _sync_coupang(self, account: MarketAccount) -> int:
        creds = account.credentials
        if not creds.get("access_key") or not creds.get("secret_key"):
            logger.warning(f"Skipping Coupang account {account.name} due to missing credentials.")
            return 0

        client = CoupangClient(
            access_key=creds.get("access_key"),
            secret_key=creds.get("secret_key"),
            vendor_id=creds.get("vendor_id")
        )
        
        # 최근 7일(쿠팡 API 제약) 조회
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        try:
            code, data = client.get_customer_inquiries(
                inquiry_start_at=start_date.strftime("%Y-%m-%d"),
                inquiry_end_at=end_date.strftime("%Y-%m-%d"),
                answered_type="NOANSWER"
            )
        except Exception as e:
            logger.error(f"Coupang connection error for {account.name}: {e}")
            return 0
        
        if code != 200:
            logger.error(f"Coupang API error (Code {code}) for {account.name}: {data}")
            return 0
            
        inquiries = data.get("data", [])
        ingested_count = 0
        for inq in inquiries:
            inquiry_id = str(inq.get("inquiryId"))
            
            # 중복 체크
            exists = self.session.execute(
                select(MarketInquiryRaw).where(
                    MarketInquiryRaw.market_code == "COUPANG",
                    MarketInquiryRaw.account_id == account.id,
                    MarketInquiryRaw.inquiry_id == inquiry_id
                )
            ).scalar_one_or_none()
            
            if not exists:
                new_inq = MarketInquiryRaw(
                    market_code="COUPANG",
                    account_id=account.id,
                    inquiry_id=inquiry_id,
                    raw=inq,
                    status="PENDING"
                )
                self.session.add(new_inq)
                ingested_count += 1
        
        self.session.commit()
        logger.info(f"Ingested {ingested_count} new Coupang inquiries for {account.name}")
        return ingested_count

    async def _sync_smartstore(self, account: MarketAccount) -> int:
        creds = account.credentials
        if not creds.get("client_id") or not creds.get("client_secret"):
            logger.warning(f"Skipping SmartStore account {account.name} due to missing credentials.")
            return 0

        client = SmartStoreClient(
            client_id=creds.get("client_id"),
            client_secret=creds.get("client_secret")
        )
        
        # 스마트스토어 미답변 문의 조회
        try:
            data = client.get_customer_inquiries(answered=False)
        except Exception as e:
            logger.error(f"SmartStore connection error for {account.name}: {e}")
            return 0
        
        inquiries = data.get("contents", [])
        ingested_count = 0
        for inq in inquiries:
            inquiry_id = str(inq.get("inquiryId"))
            
            # 중복 체크
            exists = self.session.execute(
                select(MarketInquiryRaw).where(
                    MarketInquiryRaw.market_code == "SMARTSTORE",
                    MarketInquiryRaw.account_id == account.id,
                    MarketInquiryRaw.inquiry_id == inquiry_id
                )
            ).scalar_one_or_none()
            
            if not exists:
                new_inq = MarketInquiryRaw(
                    market_code="SMARTSTORE",
                    account_id=account.id,
                    inquiry_id=inquiry_id,
                    raw=inq,
                    status="PENDING"
                )
                self.session.add(new_inq)
                ingested_count += 1
                
        self.session.commit()
        logger.info(f"Ingested {ingested_count} new SmartStore inquiries for {account.name}")
        return ingested_count
