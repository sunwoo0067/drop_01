import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, delete, func
from unittest.mock import AsyncMock, MagicMock, patch

from app.db import SessionLocal
from app.models import (
    Order, OrderItem, Product, MarketListing, MarketAccount, 
    AdaptivePolicyEvent, OrchestrationEvent, SourcingCandidate, ProductOption
)
from app.services.orchestrator_service import OrchestratorService

async def test_v150_multimarket_allocation():
    print("\n=== Coupang & SmartStore Multi-Market Allocation Verification ===")
    session = SessionLocal()
    orchestrator = OrchestratorService(db=session)
    
    try:
        # 1. Cleanup old test data
        from sqlalchemy import delete
        print("🧹 Cleaning up OrderItem...")
        session.execute(delete(OrderItem))
        session.commit()
        print("🧹 Cleaning up Order...")
        session.execute(delete(Order))
        session.commit()
        print("🧹 Cleaning up MarketListing...")
        session.execute(delete(MarketListing))
        session.commit()
        print("🧹 Cleaning up ProductOption...")
        session.execute(delete(ProductOption))
        session.commit()
        print("🧹 Cleaning up Product...")
        session.execute(delete(Product))
        session.commit()
        print("🧹 Cleaning up AdaptivePolicyEvent...")
        session.execute(delete(AdaptivePolicyEvent))
        session.commit()
        print("🧹 Cleaning up OrchestrationEvent...")
        session.execute(delete(OrchestrationEvent))
        session.commit()
        print("✨ Cleanup completed.")

        # 2. Setup Market Accounts (Ensure they exist in DB)
        # Already checked they exist as 'COUPANG' and 'SMARTSTORE'
        coupang_acc = session.execute(select(MarketAccount).where(MarketAccount.market_code == "COUPANG")).scalars().first()
        naver_acc = session.execute(select(MarketAccount).where(MarketAccount.market_code == "SMARTSTORE")).scalars().first()
        
        if not coupang_acc or not naver_acc:
            print("❌ Market accounts not found. Run verify_accounts.py first.")
            return

        # 3. Create test products
        try:
            product = Product(
                name="Test Multi-Market Product",
                supplier_item_id=None,
                cost_price=10000,
                status="ACTIVE"
            )
            session.add(product)
            session.commit() # Commit to ensure existence
            session.refresh(product)
            print(f"✅ Product created and committed: {product.id}")
            
            # Verify its existence via a new query
            exists = session.execute(select(Product).where(Product.id == product.id)).scalar()
            if exists:
                print(f"🔍 Double checked: Product {product.id} exists in DB.")
            else:
                print(f"⚠️ Warning: Product {product.id} NOT found in DB even after commit!")
        except Exception as e:
            print(f"❌ Failed to create product: {e}")
            raise

        # 4. Create Market Listings
        try:
            coupang_listing = MarketListing(
                product_id=product.id,
                market_account_id=coupang_acc.id,
                market_item_id="CP-TEST-1",
                status="ACTIVE"
            )
            naver_listing = MarketListing(
                product_id=product.id,
                market_account_id=naver_acc.id,
                market_item_id="NS-TEST-1",
                status="ACTIVE"
            )
            session.add_all([coupang_listing, naver_listing])
            session.flush()
            print(f"✅ Market Listings created: {coupang_listing.id}, {naver_listing.id}")
        except Exception as e:
            print(f"❌ Failed to create market listings: {e}")
            raise

        # 5. Populate skewed ROI data
        # Coupang: High ROI (0.3)
        # SmartStore: Low ROI (0.05)
        now = datetime.now(timezone.utc)
        
        def add_order(acc_id, listing_id, total_price, cost, count):
            for _ in range(count):
                order = Order(order_number=str(uuid.uuid4()), total_amount=total_price)
                session.add(order)
                session.flush()
                item = OrderItem(
                    order_id=order.id, 
                    product_id=product.id, 
                    market_listing_id=listing_id,
                    product_name=product.name,
                    quantity=1,
                    unit_price=total_price,
                    total_price=total_price,
                    created_at=now - timedelta(days=2)
                )
                session.add(item)

        # Coupang: 10 orders @ 15,000 (ROI 0.5)
        add_order(coupang_acc.id, coupang_listing.id, 15000, 10000, 10)
        # SmartStore: 10 orders @ 11,000 (ROI 0.1)
        add_order(naver_acc.id, naver_listing.id, 11000, 10000, 10)
        
        session.commit()

        # 6. Run Orchestrator Cycle (Mocking AI)
        mock_strategy = {
            'season_name': 'Multi-Market-Test',
            'strategy_theme': 'ROI Optimization',
            'target_keywords': ['test'],
            'out_dated_keywords': []
        }
        
        with patch('app.services.ai.service.AIService.plan_seasonal_strategy', new_callable=AsyncMock) as mock_plan:
            mock_plan.return_value = mock_strategy
            
            # Sourcing service methods that would hit external APIs or need complex setup
            orchestrator.sourcing_service.trigger_full_supplier_sync = AsyncMock()
            orchestrator.sourcing_service.import_from_raw = AsyncMock(return_value=0)
            orchestrator.sourcing_service.execute_expanded_sourcing = AsyncMock()
            orchestrator.run_continuous_processing = AsyncMock()
            orchestrator.run_continuous_listing = AsyncMock()
            
            await orchestrator.run_daily_cycle(dry_run=True)

        # 7. Verification
        event = session.execute(
            select(OrchestrationEvent)
            .where(OrchestrationEvent.step == "PLANNING")
            .order_by(OrchestrationEvent.created_at.desc())
        ).scalars().first()

        print(f"\nPlanning Event Message: {event.message}")
        quotas = event.details.get("market_quotas", {})
        print(f"Quotas: {quotas}")
        
        reports = event.details.get("market_reports", {})
        cp_roi = reports.get("COUPANG", {}).get("health", {}).get("current_roi")
        ns_roi = reports.get("SMARTSTORE", {}).get("health", {}).get("current_roi")
        
        print(f"Coupang ROI: {cp_roi}, SmartStore ROI: {ns_roi}")

        assert quotas["COUPANG"] > quotas["SMARTSTORE"], "Coupang should have more quota due to higher ROI"
        print("✅ Multi-Market Capital Allocation Verified!")

    finally:
        session.close()

if __name__ == "__main__":
    asyncio.run(test_v150_multimarket_allocation())
