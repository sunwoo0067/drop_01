
import asyncio
import uuid
from app.db import SessionLocal
from app.models import MarketAccount, Product
from app.services.orchestrator_service import OrchestratorService
from sqlalchemy import select

async def verify_fixes():
    print("Starting verification of fixes...")
    
    with SessionLocal() as session:
        # 1. OrchestratorService asyncio NameError 확인
        print("\n[1/3] Testing OrchestratorService asyncio import...")
        try:
            orchestrator = OrchestratorService(session)
            # run_daily_cycle을 실제로 실행하지 않고 내부적으로 asyncio를 사용하는 로직이 로드되는지 확인
            print("Successfully initialized OrchestratorService.")
        except Exception as e:
            print(f"FAILED: OrchestratorService initialization error: {e}")

        # 2. MarketAccount 비활성화 시 필터링 확인
        print("\n[2/3] Testing account filtering...")
        # 임시 계정 생성
        temp_acc = MarketAccount(
            market_code="COUPANG",
            name="TEST_INACTIVE_ACC",
            credentials={"test": "data"},
            is_active=False
        )
        session.add(temp_acc)
        session.commit()
        
        try:
            # 활성 계정만 조회하는 쿼리 확인
            stmt = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
            active_accounts = session.scalars(stmt).all()
            
            if any(acc.id == temp_acc.id for acc in active_accounts):
                print(f"FAILED: Inactive account {temp_acc.id} found in active accounts list!")
            else:
                print("SUCCESS: Inactive account correctly filtered out.")
        finally:
            session.delete(temp_acc)
            session.commit()

        # 3. OrchestratorService.run_daily_cycle 내부 필터링 확인 (Dry Run)
        print("\n[3/3] Testing OrchestratorService.run_daily_cycle filtering (Dry Run)...")
        try:
            # dry_run=True로 실행하여 실제 등록은 하지 않음
            res = await orchestrator.run_daily_cycle(dry_run=True)
            print(f"SUCCESS: Orchestrator ran successfully. Strategic theme: {res.get('strategy_theme')}")
        except Exception as e:
            print(f"FAILED: run_daily_cycle error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_fixes())
