from app.session_factory import session_factory
from app.models import MarketAccount
from sqlalchemy import select

with session_factory() as session:
    accounts = session.execute(select(MarketAccount)).scalars().all()
    for acc in accounts:
        print(f"ID: {acc.id}, Market: {acc.market_code}, Name: {acc.name}, Active: {acc.is_active}")
