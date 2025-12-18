import uuid
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import SessionLocal
from app.models import MarketListing, MarketAccount
from app.coupang_sync import sync_market_listing_status

def test_sync():
    session = SessionLocal()
    try:
        # Get a sample market listing that is linked to Coupang
        listing = session.query(MarketListing).filter(MarketListing.market_item_id != None).first()
        
        if not listing:
            print("No market listings found to test with.")
            return

        print(f"Testing status sync for Listing ID: {listing.id}, Market Item ID: {listing.market_item_id}")
        
        success, result = sync_market_listing_status(session, listing.id)
        
        if success:
            print(f"Sync Success! New Coupang Status: {result}")
            # Re-fetch to check if rejection_reason or coupang_status is updated
            session.refresh(listing)
            print(f"Stored Coupang Status in DB: {listing.coupang_status}")
            if listing.rejection_reason:
                print(f"Rejection Reason found: {listing.rejection_reason}")
        else:
            print(f"Sync Failed: {result}")

    except Exception as e:
        print(f"An error occurred during testing: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    test_sync()
