import asyncio
import uuid
from sqlalchemy import select, delete
from app.db import SessionLocal
from app.models import MarketAccount, MarketListing, PricingRecommendation, PriceChangeLog, PricingSettings, MarketInquiryRaw, MarketOrderRaw, MarketProductRaw, OrderItem, Order
from app.api.endpoints.settings import delete_coupang_account

async def debug_deletion():
    session = SessionLocal()
    acc_id = uuid.UUID("bec0525d-8469-4ac2-bc36-31458ed06637")
    acc = session.get(MarketAccount, acc_id)
    
    if not acc:
        print(f"Account {acc_id} not found.")
        return
    
    print(f"Debugging deletion of account {acc.name} ({acc.id})")
    
    # Check if there are PricingRecommendations
    recs = session.scalars(select(PricingRecommendation).where(PricingRecommendation.market_account_id == acc_id)).all()
    print(f"Found {len(recs)} PricingRecommendations.")
    
    try:
        # Manually try the steps and print results
        print("Step 1: Unlinking OrderItems...")
        listing_ids = session.scalars(select(MarketListing.id).where(MarketListing.market_account_id == acc_id)).all()
        if listing_ids:
            res = session.query(OrderItem).filter(OrderItem.market_listing_id.in_(listing_ids)).update({"market_listing_id": None}, synchronize_session=False)
            print(f"Unlinked {res} OrderItems.")
        
        print("Step 2: Unlinking Orders...")
        raw_ids = session.scalars(select(MarketOrderRaw.id).where(MarketOrderRaw.account_id == acc_id)).all()
        if raw_ids:
            res = session.query(Order).filter(Order.market_order_id.in_(raw_ids)).update({"market_order_id": None}, synchronize_session=False)
            print(f"Unlinked {res} Orders.")
            
        print("Step 3: Deleting PricingRecommendations...")
        res = session.execute(delete(PricingRecommendation).where(PricingRecommendation.market_account_id == acc_id))
        print(f"Deleted recommendations: {res.rowcount}")
        
        print("Step 4: Deleting other dependencies...")
        session.execute(delete(PriceChangeLog).where(PriceChangeLog.market_account_id == acc_id))
        session.execute(delete(PricingSettings).where(PricingSettings.market_account_id == acc_id))
        session.execute(delete(MarketListing).where(MarketListing.market_account_id == acc_id))
        session.execute(delete(MarketOrderRaw).where(MarketOrderRaw.account_id == acc_id))
        session.execute(delete(MarketProductRaw).where(MarketProductRaw.account_id == acc_id))
        session.execute(delete(MarketInquiryRaw).where(MarketInquiryRaw.account_id == acc_id))
        
        print("Step 5: Deleting MarketAccount...")
        session.delete(acc)
        
        print("Step 6: Committing...")
        session.commit()
        print("SUCCESS: Committed deletion.")
        
    except Exception as e:
        print(f"FAILURE: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    asyncio.run(debug_deletion())
