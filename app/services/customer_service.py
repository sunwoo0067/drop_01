import logging
import uuid
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.models import MarketInquiryRaw, MarketListing, Product
from app.services.ai.service import AIService
from app.services.ai.agents.cs_workflow_agent import CSWorkflowAgent

logger = logging.getLogger(__name__)

class CustomerService:
    def __init__(self, ai_service: Optional[AIService] = None):
        self.ai_service = ai_service or AIService()

    async def generate_replies_for_unanswered_inquiries(self, session: Session, market_code: str = "COUPANG"):
        """
        답변이 생성되지 않은 문의들에 대해 AI 답변 초안을 생성합니다.
        """
        # 1. 답변 초안이 없는 문의 조회
        stmt = (
            select(MarketInquiryRaw)
            .where(
                and_(
                    MarketInquiryRaw.market_code == market_code,
                    MarketInquiryRaw.status == "PENDING"
                )
            )
            .limit(50)
        )
        inquiries = session.execute(stmt).scalars().all()
        
        print(f"Found {len(inquiries)} pending inquiries for {market_code}")
        if not inquiries:
            logger.info(f"No unanswered inquiries found for {market_code}")
            return

        cs_agent = CSWorkflowAgent(session)

        for inquiry in inquiries:
            try:
                await self._process_single_inquiry(session, inquiry, cs_agent)
            except Exception as e:
                logger.error(f"Failed to process inquiry {inquiry.inquiry_id}: {e}")
                continue
        
        session.commit()

    async def _process_single_inquiry(self, session: Session, inquiry: MarketInquiryRaw, cs_agent: CSWorkflowAgent):
        raw_data = inquiry.raw
        
        seller_product_id = raw_data.get("sellerProductId")
        content = raw_data.get("content", "")
        
        product_info = {}
        if seller_product_id:
            # 상품 정보 조회
            listing = session.execute(
                select(MarketListing).where(
                    and_(
                        MarketListing.market_account_id == inquiry.account_id,
                        MarketListing.market_item_id == str(seller_product_id)
                    )
                )
            ).scalar_one_or_none()

            if listing:
                product = session.execute(
                    select(Product).where(Product.id == listing.product_id)
                ).scalar_one_or_none()
                
                if product:
                    product_info = {
                        "id": str(product.id),
                        "name": product.processed_name or product.name,
                        "description": product.description[:1000]
                    }

        # CS 에이전트 실행
        input_data = {
            "inquiry_id": inquiry.id,
            "content": content,
            "market_code": inquiry.market_code,
            "product_info": product_info
        }

        try:
            result = await cs_agent.run_cs(input_data)
            if "error" in result:
                logger.error(f"CS Agent failed for inquiry {inquiry.inquiry_id}: {result['error']}")
            else:
                logger.info(f"Generated AI answer for inquiry {inquiry.inquiry_id} (Status: {result.get('status')})")
        except Exception as e:
            logger.error(f"CS Agent execution error for inquiry {inquiry.inquiry_id}: {e}")
