from app.db import SessionLocal
from app.models import MarketAccount, MarketListing
import uuid

def check_accounts():
    session = SessionLocal()
    print("--- Market Accounts (All) ---")
    accounts = session.query(MarketAccount).all()
    for acc in accounts:
        print(f"ID: {acc.id}, Name: {acc.name}, Code: {acc.market_code}, Active: {acc.is_active}")
    
    print("\n--- Market Listings Summary ---")
    # Join with MarketAccount to see if accounts exist
    from sqlalchemy import select, func
    stmt_stats = (
        select(MarketListing.market_account_id, func.count(MarketListing.id))
        .group_by(MarketListing.market_account_id)
    )
    stats_rows = session.execute(stmt_stats).all()
    for row in stats_rows:
        acc_id, count = row
        acc = session.query(MarketAccount).get(acc_id)
        if acc:
            print(f"Account ID: {acc_id}, Name: {acc.name}, Active: {acc.is_active}, Listings: {count}")
        else:
            print(f"Account ID: {acc_id}, Name: [DELETED], Listings: {count}")
            
    session.close()

if __name__ == "__main__":
    check_accounts()
