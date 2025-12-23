import asyncio
import logging
import uuid
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import MarketAccount, Product, MarketListing
from app.services.orchestrator_service import OrchestratorService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_multimarket_simple():
    print("--- SIMPLE VERIFICATION STARTED ---")
    session_gen = get_session()
    db: Session = next(session_gen)

    RANDOM_ID = str(uuid.uuid4())[:8]
    UNIQUE_KEYWORD = f"FORCED-DEL-{RANDOM_ID}"
    TEST_NAME = f"[{UNIQUE_KEYWORD}] 가을 배색 점퍼"

    try:
        # 1. 계정 확인
        smartstore_acc = db.query(MarketAccount).filter(MarketAccount.market_code == "SMARTSTORE").first()
        coupang_acc = db.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG").first()
        
        if not smartstore_acc or not coupang_acc:
            print("Required accounts (SMARTSTORE, COUPANG) missing. Please ensure they exist.")
            return

        # 2. 테스트 데이터 생성
        test_product = Product(
            id=uuid.uuid4(),
            name=TEST_NAME,
            status="ACTIVE",
            processing_status="COMPLETED"
        )
        db.add(test_product)
        db.commit()

        db.add(MarketListing(
            id=uuid.uuid4(),
            product_id=test_product.id,
            market_account_id=coupang_acc.id,
            market_item_id=f"CP_TEST_{RANDOM_ID}",
            status="ACTIVE"
        ))
        
        db.add(MarketListing(
            id=uuid.uuid4(),
            product_id=test_product.id,
            market_account_id=smartstore_acc.id,
            market_item_id=f"SS_TEST_{RANDOM_ID}",
            status="ACTIVE"
        ))
        db.commit()
        print(f"Test data created: {TEST_NAME}")

        # 3. 서비스 초기화 및 검증 로직
        orchestrator = OrchestratorService(db)
        
        # AnalysisAgent 직접 호출하여 매칭 확인
        print(f"Testing cleanup target detection for keyword: {UNIQUE_KEYWORD}")
        cleanup_targets = orchestrator.analysis_agent.find_cleanup_targets([UNIQUE_KEYWORD])
        
        print(f"Detected {len(cleanup_targets)} targets.")
        for item in cleanup_targets:
            m_code = item.get("market_code")
            print(f"[FOUND] {item['name']} on {m_code} (ID: {item['market_item_id']})")
            
            # MarketService 호출 검증 (Dry-run 성격으로 호출 결과만 확인)
            ok, err = orchestrator.market_service.delete_product(m_code, uuid.UUID(item['market_account_id']), item['market_item_id'])
            print(f"[DELETE-RESULT] {m_code}: {ok}, Error: {err}")

        print("--- SIMPLE VERIFICATION FINISHED ---")

    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(verify_multimarket_simple())
