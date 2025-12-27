from app.session_factory import session_factory
from app.models import MarketAccount
from sqlalchemy import select

with session_factory() as session:
    acc = session.execute(select(MarketAccount).where(MarketAccount.market_code == "SMARTSTORE")).scalars().first()
    print(f"Name: {acc.name}")
    print(f"Credentials: {acc.credentials}")
