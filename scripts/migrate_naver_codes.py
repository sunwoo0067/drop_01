from app.db import SessionLocal
from app.models import MarketAccount, MarketListing, MarketOrderRaw, MarketProductRaw, MarketInquiryRaw
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_naver_to_smartstore():
    session = SessionLocal()
    try:
        # 1. Update MarketAccount market_code
        # Note: We need to be careful if there's a unique constraint on (market_code, name)
        # uq_market_accounts_code_name = UniqueConstraint("market_code", "name")
        
        accounts = session.query(MarketAccount).filter(MarketAccount.market_code == "NAVER").all()
        logger.info(f"Found {len(accounts)} accounts with market_code 'NAVER'")
        
        for acc in accounts:
            logger.info(f"Migrating account: {acc.name} ({acc.id})")
            # Check if an account with 'SMARTSTORE' and the same name already exists
            existing = session.query(MarketAccount).filter(
                MarketAccount.market_code == "SMARTSTORE",
                MarketAccount.name == acc.name
            ).first()
            
            if existing:
                logger.warning(f"Account with name '{acc.name}' already exists as 'SMARTSTORE'. Skipping automated rename for safety.")
                # In this case we might need manual intervention or merge, but for now let's just log it.
                continue
            
            acc.market_code = "SMARTSTORE"
        
        # 2. Update MarketListing market_code if applicable
        # Let's check if MarketListing has market_code. Looking at models.py earlier, it might.
        # Check attributes of MarketListing
        has_market_code = hasattr(MarketListing, "market_code")
        if has_market_code:
            listings = session.query(MarketListing).filter(MarketListing.market_code == "NAVER").all()
            logger.info(f"Updating {len(listings)} listings from NAVER to SMARTSTORE")
            for l in listings:
                l.market_code = "SMARTSTORE"
        
        session.commit()
        logger.info("Migration completed successfully.")
    except Exception as e:
        session.rollback()
        logger.error(f"Migration failed: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    migrate_naver_to_smartstore()
