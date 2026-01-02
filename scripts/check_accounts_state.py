from app.db import SessionLocal
from app.models import MarketAccount, MarketListing
import uuid

def check_accounts():
    session = SessionLocal()
    print("--- Market Accounts ---")
    accounts = session.query(MarketAccount).all()
    for acc in accounts:
        print(f"ID: {acc.id}, Name: {acc.name}, Code: {acc.market_code}, Active: {acc.is_active}")
    
    print("\n--- Market Listings by Account ---")
    listings = session.query(MarketListing.market_account_id).distinct().all()
    for l in listings:
        acc_id = l[0]
        count = session.query(MarketListing).filter(MarketListing.market_account_id == acc_id).count()
        acc = session.get(MarketAccount, acc_id)
        if acc:
            print(f"Account ID: {acc_id} ({acc.name}) - Listings: {count}")
        else:
            print(f"Account ID: {acc_id} (DELETED/NOT FOUND) - Listings: {count}")
            
    session.close()

if __name__ == "__main__":
    check_accounts()
