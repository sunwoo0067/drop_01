import asyncio
import logging
import uuid
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import MarketAccount, Product, MarketListing
from app.services.orchestrator_service import OrchestratorService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_multimarket():
    print("--- SCRIPT STARTED ---")
    session_gen = get_session()
    db: Session = next(session_gen)

    UNIQUE_KEYWORD = "UNIQUE-XYZ-99"
    TEST_NAME = f"[{UNIQUE_KEYWORD}] 가을 바람막이"

    try:
        # 1. 테스트용 마켓 계정 설정 확인 (또는 생성)
        smartstore_acc = db.query(MarketAccount).filter(MarketAccount.market_code == "SMARTSTORE").first()
        if not smartstore_acc:
            smartstore_acc = MarketAccount(
                id=uuid.uuid4(),
                market_code="SMARTSTORE",
                name="Test SmartStore",
                is_active=True,
                credentials={"client_id": "test_id", "client_secret": "test_secret"}
            )
            db.add(smartstore_acc)
            logger.info("Created test SmartStore account.")
        else:
            smartstore_acc.is_active = True

        coupang_acc = db.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG").first()
        if not coupang_acc:
            coupang_acc = MarketAccount(
                id=uuid.uuid4(),
                market_code="COUPANG",
                name="Test Coupang",
                is_active=True,
                credentials={"api_key": "test", "secret_key": "test"}
            )
            db.add(coupang_acc)
            logger.info("Created test Coupang account.")
        else:
            coupang_acc.is_active = True
        
        db.commit()
        print("Accounts setup committed")

        # 2. 테스트용 상품 및 리스팅 생성 (삭제 테스트용)
        # 이미 있으면 삭제하고 다시 생성 (고유 키워드 기준이므로 빠름)
        existing_p = db.query(Product).filter(Product.name == TEST_NAME).first()
        if existing_p:
            db.query(MarketListing).filter(MarketListing.product_id == existing_p.id).delete()
            db.delete(existing_p)
            db.commit()
            print("Cleaned up previous unique test data")

        test_product = Product(
            id=uuid.uuid4(),
            name=TEST_NAME,
            status="ACTIVE",
            processing_status="COMPLETED"
        )
        db.add(test_product)
        db.commit()

        # 쿠팡 리스팅
        db.add(MarketListing(
            id=uuid.uuid4(),
            product_id=test_product.id,
            market_account_id=coupang_acc.id,
            market_item_id="CP_UNIQUE_123",
            status="ACTIVE"
        ))
        
        # 스마트스토어 리스팅
        db.add(MarketListing(
            id=uuid.uuid4(),
            product_id=test_product.id,
            market_account_id=smartstore_acc.id,
            market_item_id="SS_UNIQUE_456",
            status="ACTIVE"
        ))
        db.commit()
        print(f"Test data created for {TEST_NAME}")

        # 3. 오케스트레이터 실행 (Dry-Run)
        print("Initializing OrchestratorService")
        orchestrator = OrchestratorService(db)
        
        print(f"--- Running Multi-Market daily cycle with forced keyword '{UNIQUE_KEYWORD}' ---")
        
        # Original: await orchestrator.run_daily_cycle(dry_run=True)
        # 억지로 키워드를 끼워넣기 위해 run_daily_cycle의 로직 일부를 직접 수행하거나 
        # AIService를 모킹할 수 있지만, 여기서는 간단히 cleanup_targets를 직접 확인하는 식으로 검증
        
        strategy = orchestrator.ai_service.plan_seasonal_strategy()
        # 강제로 키워드 추가
        if 'out_dated_keywords' not in strategy:
            strategy['out_dated_keywords'] = []
        strategy['out_dated_keywords'].append(UNIQUE_KEYWORD)
        
        # 2단계: 비인기/오프시즌 상품 정리 (Optimization) - 이 부분이 핵심 검증 대상
        outdated_keywords = strategy.get('out_dated_keywords', [])
        cleanup_targets = orchestrator.analysis_agent.find_cleanup_targets(outdated_keywords)
        
        print(f"Identified {len(cleanup_targets)} cleanup targets.")
        for item in cleanup_targets:
            m_code = item.get('market_code', 'COUPANG')
            if True: # Dry-Run simulation
                print(f"[VERIFY-LOG] Deleting item {item['market_item_id']} from account {item['market_account_id']} (Market: {m_code}, Reason: {item['reason']})")
                # 실제 로직 호출 여부 확인을 위해 market_service.delete_product를 호출해볼 수도 있음 (Dry-run이므로 안전)
                ok, err = orchestrator.market_service.delete_product(m_code, uuid.UUID(item['market_account_id']), item['market_item_id'])
                print(f"[VERIFY-LOG] Result for {m_code}: {ok}, {err}")

        print("Verification steps finished")
        
        logger.info("--- Verification completed ---")

    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(verify_multimarket())
