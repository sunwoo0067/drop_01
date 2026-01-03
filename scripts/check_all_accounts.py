from app.session_factory import session_factory
from app.models import MarketAccount
from sqlalchemy import select

with session_factory() as session:
    accounts = session.execute(select(MarketAccount)).scalars().all()
    for acc in accounts:
        creds = acc.credentials or {}
        print(f"Market: {acc.market_code}, ID: {acc.id}, Name: {acc.name}")
        for k, v in creds.items():
            if v:
                val = str(v)
                print(f"  {k}: [{val[:4]}...{val[-4:] if len(val)>4 else ''}] (len: {len(val)})")
        print("-" * 20)
