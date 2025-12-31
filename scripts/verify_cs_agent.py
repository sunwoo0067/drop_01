print("Starting script...")
import asyncio
import logging
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from app.db import SessionLocal
from app.models import MarketInquiryRaw, MarketListing, Product, MarketAccount
from app.services.customer_service import CustomerService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_cs_agent():
    session = SessionLocal()
    cs_service = CustomerService()
    
    test_inquiry_id = str(uuid.uuid4())
    account_id = None
    
    try:
        # 0. 테스트용 마켓 계정 조회 또는 생성
        account = session.execute(select(MarketAccount).limit(1)).scalar_one_or_none()
        if not account:
            logger.error("No MarketAccount found. Please run a script to create one first.")
            return
        account_id = account.id

        # 1. 테스트용 문의 생생 (PENDING 상태)
        test_inquiry = MarketInquiryRaw(
            market_code="COUPANG",
            account_id=account_id,
            inquiry_id=test_inquiry_id,
            raw={
                "content": "이 상품 배송이 얼마나 걸릴까요? 그리고 변압기가 필요한가요?",
                "inquiryTypeName": "배송/상품문의",
                "sellerProductId": "test_prod_123"
            },
            status="PENDING"
        )
        session.add(test_inquiry)
        session.commit()
        print(f"Created test inquiry: {test_inquiry_id}")
        session.close() # Deadlock 방지: AIService가 내부에서 새로운 세션을 열 수 있도록 닫음

        # 2. CS 서비스 실행
        print("Running CustomerService.generate_replies_for_unanswered_inquiries...")
        # CustomerService는 내부적으로 필요할 때마다 새로운 세션을 열거나 전달된 세션을 사용할 수 있어야 함.
        # 여기서는 SessionLocal()을 사용하는 대신 cs_service에 맡김 (또는 내부적으로 세션을 새로 생성하도록 유도)
        with SessionLocal() as service_session:
            await cs_service.generate_replies_for_unanswered_inquiries(service_session, market_code="COUPANG")
        
        # 3. 결과 검증
        session = SessionLocal() # 검증용 세션 새로 열기
        updated_inquiry = session.execute(
            select(MarketInquiryRaw).where(MarketInquiryRaw.inquiry_id == test_inquiry_id)
        ).scalar_one_or_none()
        
        if not updated_inquiry:
            print("ERROR: Test inquiry disappeared!")
            return

        print("--- Verification Results ---")
        print(f"Status: {updated_inquiry.status}")
        print(f"Confidence Score: {updated_inquiry.confidence_score}")
        print(f"AI Suggested Answer: {updated_inquiry.ai_suggested_answer}")
        print(f"Metadata: {updated_inquiry.cs_metadata}")
        
        if updated_inquiry.status in ["AI_DRAFTED", "HUMAN_REVIEW"] and updated_inquiry.ai_suggested_answer:
            print("✅ SUCCESS: CS Agent successfully processed the inquiry.")
        else:
            print("❌ FAILURE: CS Agent did not process the inquiry correctly.")

    except Exception as e:
        print(f"ERROR: Verification failed with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 4. 테스트 데이터 삭제 (Cleanup)
        print("Cleaning up test data...")
        session.execute(delete(MarketInquiryRaw).where(MarketInquiryRaw.inquiry_id == test_inquiry_id))
        session.commit()
        session.close()

if __name__ == "__main__":
    asyncio.run(verify_cs_agent())
