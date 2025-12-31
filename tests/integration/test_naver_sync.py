import pytest
import uuid
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models import MarketAccount, Order, OrderItem, QnaThread, QnaMessage, SyncRun, SyncCursor
from app.sync.naver_order_sync import NaverOrderSync
from app.sync.naver_qna_sync import NaverQnaSync
from app.services.agents.cs_agent import CSAgent

@pytest.fixture
def db_session():
    session = SessionLocal()
    yield session
    session.close()

@pytest.fixture
def naver_account(db_session):
    account = MarketAccount(
        name=f"test_naver_{uuid.uuid4().hex[:4]}",
        market_code="NAVER",
        credentials={"client_id": "test_id", "client_secret": "test_secret"},
        is_active=True
    )
    db_session.add(account)
    db_session.commit()
    return account

def test_naver_order_sync_mock(db_session, naver_account):
    """네이버 주문 동기화 통합 테스트 (Mock)"""
    sync = NaverOrderSync(db_session, naver_account)
    
    mock_order = {
        "orderId": "20231231-123456",
        "productOrderNo": "9999999",
        "productOrderStatus": "PAYED",
        "productName": "테스트 상품",
        "orderDate": "2023-12-31T15:00:00.000+09:00",
        "shippingAddress": {
            "name": "홍길동",
            "tel1": "010-1234-5678",
            "baseAddress": "서울시 강남구",
            "detailedAddress": "테헤란로 123"
        }
    }
    
    with patch.object(sync.client, "get_changed_product_orders") as mock_get:
        mock_get.return_value = {
            "data": [{"productOrder": mock_order}],
            "more": None
        }
        
        sync.run()
        
    # 검증: Order 생성 확인
    order = db_session.query(Order).filter_by(vendor_order_id="20231231-123456").first()
    assert order is not None
    assert order.status == "PAYED"
    assert order.recipient_name == "홍길동"
    
    # 검증: OrderItem 생성 확인
    item = db_session.query(OrderItem).filter_by(vendor_item_id="9999999").first()
    assert item is not None
    assert item.order_id == order.id

def test_naver_qna_and_cs_agent_mock(db_session, naver_account):
    """네이버 QnA 동기화 및 CSAgent 초안 생성 테스트 (Mock)"""
    qna_sync = NaverQnaSync(db_session, naver_account)
    
    mock_qna = {
        "inquiryId": "QNA_12345",
        "isAnswered": False,
        "content": "배송은 언제 되나요?",
        "inquiryType": "DELIVERY"
    }
    
    with patch.object(qna_sync.client, "get_customer_inquiries") as mock_get:
        mock_get.return_value = {
            "contents": [mock_qna]
        }
        qna_sync.run()
        
    # 검증: QnaThread 생성 확인
    thread = db_session.query(QnaThread).filter_by(vendor_thread_id="QNA_12345").first()
    assert thread is not None
    assert thread.status == "OPEN"
    
    # 검증: Message 생성 확인
    msg = db_session.query(QnaMessage).filter_by(thread_id=thread.id, direction="IN").first()
    assert msg is not None
    assert "배송" in msg.body
    
    # CSAgent 테스트 (Mock AI)
    agent = CSAgent(db_session)
    with patch.object(agent.ai_service, "generate_text", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "안녕하세요. 곧 배송해드리겠습니다."
        
        asyncio.run(agent.process_pending_threads())
        
    # 검증: 초안 생성 확인
    db_session.expire_all() # 세션 강제 갱신
    thread = db_session.query(QnaThread).filter_by(vendor_thread_id="QNA_12345").first()
    assert "ai_draft" in thread.raw, f"AI draft not found in thread.raw: {thread.raw}"
    assert thread.raw["ai_draft"]["content"] == "안녕하세요. 곧 배송해드리겠습니다."
