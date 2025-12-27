
from app.db import SessionLocal
from app.models import MarketAccount, MarketListing
from sqlalchemy import select

def check_accounts():
    with SessionLocal() as session:
        # 모든 마켓 계정 조회
        stmt = select(MarketAccount).order_by(MarketAccount.market_code, MarketAccount.name)
        accounts = session.scalars(stmt).all()
        
        print(f"{'Market':<12} | {'Name':<20} | {'Active':<8} | {'ID'}")
        print("-" * 70)
        
        for acc in accounts:
            # 해당 계정의 리스팅 수 확인
            listing_count = session.query(MarketListing).filter(MarketListing.market_account_id == acc.id).count()
            print(f"{acc.market_code:<12} | {acc.name:<20} | {str(acc.is_active):<8} | {acc.id} (Listings: {listing_count})")

if __name__ == "__main__":
    check_accounts()
