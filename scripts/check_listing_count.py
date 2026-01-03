from app.session_factory import session_factory
from app.models import MarketListing
from sqlalchemy import select, func

with session_factory() as session:
    count = session.execute(select(func.count(MarketListing.id))).scalar()
    print(f"Total registered products (MarketListing): {count}")
    
    # By market
    from app.models import MarketAccount
    stmt = select(MarketAccount.market_code, func.count(MarketListing.id)).join(MarketListing, MarketAccount.id == MarketListing.market_account_id).group_by(MarketAccount.market_code)
    results = session.execute(stmt).all()
    for market, m_count in results:
        print(f"{market}: {m_count}")
