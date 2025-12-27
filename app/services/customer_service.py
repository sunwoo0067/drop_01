import logging
import uuid
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.models import MarketInquiryRaw, MarketListing, Product
from app.services.ai.service import AIService

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
                    MarketInquiryRaw.ai_suggested_answer == None
                )
            )
            .limit(50)  # 한 번에 너무 많이 처리하지 않도록 제한
        )
        inquiries = session.execute(stmt).scalars().all()
        
        if not inquiries:
            logger.info(f"No unanswered inquiries found for {market_code}")
            return

        for inquiry in inquiries:
            try:
                await self._process_single_inquiry(session, inquiry)
            except Exception as e:
                logger.error(f"Failed to process inquiry {inquiry.inquiry_id}: {e}")
                continue
        
        session.commit()

    async def _process_single_inquiry(self, session: Session, inquiry: MarketInquiryRaw):
        raw_data = inquiry.raw
        
        # 쿠팡 고객문의 구조에 따라 상품 식별 추출 (inquiryType에 따라 다를 수 있음)
        # 일반 고객문의는 sellerProductId가 포함됨
        seller_product_id = raw_data.get("sellerProductId")
        content = raw_data.get("content", "")
        inquiry_type = raw_data.get("inquiryTypeName", "일반문의")
        
        if not seller_product_id:
            logger.warning(f"No sellerProductId found for inquiry {inquiry.inquiry_id}")
            return

        # 상품 정보 조회
        listing = session.execute(
            select(MarketListing).where(
                and_(
                    MarketListing.market_account_id == inquiry.account_id,
                    MarketListing.market_item_id == str(seller_product_id)
                )
            )
        ).scalar_one_or_none()

        product = None
        if listing:
            product = session.execute(
                select(Product).where(Product.id == listing.product_id)
            ).scalar_one_or_none()

        # 답변 생성을 위한 프롬프트 구성
        product_context = ""
        if product:
            product_context = f"""
            [상품 정보]
            - 상품명: {product.processed_name or product.name}
            - 설명: {product.description[:500]}
            """

        prompt = f"""
        당신은 친절한 쇼핑몰 고객센터 상담원입니다. 
        고객님의 문의에 대해 정중하고 상세하게 답변을 작성해주세요.
        
        {product_context}
        
        [고객 문의]
        - 유형: {inquiry_type}
        - 내용: {content}
        
        [답변 가이드라인]
        - 정중한 문체를 사용하세요 (예: ~입니다, ~해요).
        - 답변이 불확실한 경우(예: 정확한 재고 상황 등)는 '담당자 확인 후 안내드리겠다'는 내용을 포함하세요.
        - 상품 정보가 있는 경우 이를 최대한 활용하여 답변하세요.
        - 한국어로만 답변하세요.
        
        답변 초안 바로 시작:
        """

        try:
            answer_text = await self.ai_service.generate_text(prompt, provider="auto")
            
            inquiry.ai_suggested_answer = answer_text.strip()
            logger.info(f"Generated AI answer for inquiry {inquiry.inquiry_id}")
            
        except Exception as e:
            logger.error(f"AI generation failed for inquiry {inquiry.inquiry_id}: {e}")
