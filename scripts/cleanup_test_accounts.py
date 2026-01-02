from app.db import SessionLocal
from app.models import MarketAccount, MarketListing, MarketOrderRaw, MarketProductRaw, MarketInquiryRaw, PricingRecommendation, PriceChangeLog, PricingSettings, Order, OrderItem
from sqlalchemy import select, delete
import logging
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup_test_accounts():
    session = SessionLocal()
    try:
        # Identify "API Test Acc" accounts
        accounts = session.query(MarketAccount).filter(MarketAccount.name.like("API Test Acc%")).all()
        logger.info(f"Found {len(accounts)} test accounts to evaluate for cleanup")
        
        for acc in accounts:
            account_id = acc.id
            # Check for listings
            listing_count = session.query(MarketListing).filter(MarketListing.market_account_id == account_id).count()
            
            if listing_count == 0:
                logger.info(f"Cleaning up test account: {acc.name} ({account_id}) - No listings found.")
                
                # Perform full deletion sequence (copied from settings.py logic)
                # 1. OrderItem unlinking
                session.query(OrderItem).filter(OrderItem.market_listing_id.in_(
                    select(MarketListing.id).where(MarketListing.market_account_id == account_id)
                )).update({"market_listing_id": None}, synchronize_session=False)

                # 2. Order unlinking
                session.query(Order).filter(Order.market_order_id.in_(
                    select(MarketOrderRaw.id).where(MarketOrderRaw.account_id == account_id)
                )).update({"market_order_id": None}, synchronize_session=False)

                # 3. Dependent deletes
                session.execute(delete(PricingRecommendation).where(PricingRecommendation.market_account_id == account_id))
                session.execute(delete(PriceChangeLog).where(PriceChangeLog.market_account_id == account_id))
                session.execute(delete(PricingSettings).where(PricingSettings.market_account_id == account_id))
                
                session.execute(delete(MarketListing).where(MarketListing.market_account_id == account_id))
                session.execute(delete(MarketOrderRaw).where(MarketOrderRaw.account_id == account_id))
                session.execute(delete(MarketProductRaw).where(MarketProductRaw.account_id == account_id))
                session.execute(delete(MarketInquiryRaw).where(MarketInquiryRaw.account_id == account_id))

                # 4. Final account delete
                session.delete(acc)
            else:
                logger.info(f"Skipping test account: {acc.name} ({account_id}) - Has {listing_count} listings.")

        session.commit()
        logger.info("Cleanup completed successfully.")
    except Exception as e:
        session.rollback()
        logger.error(f"Cleanup failed: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    cleanup_test_accounts()
