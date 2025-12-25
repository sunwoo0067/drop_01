from app.session_factory import session_factory
from app.models import MarketAccount
from sqlalchemy import select
import sys

with session_factory() as session:
    acc = session.execute(select(MarketAccount).where(MarketAccount.market_code == "SMARTSTORE")).scalars().first()
    if not acc:
        print("No account found")
        sys.exit(0)
    secret = acc.credentials.get("client_secret", "")
    print(f"VAL: {secret}")
    print(f"LEN: {len(secret)}")
