import os
import sys
from datetime import datetime, timezone, timedelta

from app.db import SessionLocal
from app.models import MarketAccount, CoupangCategoryMetaCache
from app.coupang_client import CoupangClient


def _get_client(session):
    account = session.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG").first()
    if not account or not isinstance(account.credentials, dict):
        raise RuntimeError("No Coupang credentials found")
    return CoupangClient(account.credentials["access_key"], account.credentials["secret_key"], account.credentials["vendor_id"])


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/refresh_coupang_category_meta_cache.py <category_code> [category_code ...]")
        return 1

    codes = [str(c).strip() for c in sys.argv[1:] if str(c).strip()]
    ttl_hours = 24
    try:
        ttl_hours = int(os.getenv("COUPANG_CATEGORY_META_TTL_HOURS", "24"))
    except Exception:
        ttl_hours = 24

    with SessionLocal() as session:
        client = _get_client(session)
        updated = 0
        for code in codes:
            http, data = client.get_category_meta(code)
            if http != 200 or not isinstance(data, dict) or not isinstance(data.get("data"), dict):
                print(f"skip {code}: http={http}")
                continue
            meta = data["data"]
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=max(1, ttl_hours))

            row = session.query(CoupangCategoryMetaCache).filter(CoupangCategoryMetaCache.category_code == code).first()
            if row:
                row.meta = meta
                row.fetched_at = now
                row.expires_at = expires_at
            else:
                session.add(
                    CoupangCategoryMetaCache(
                        category_code=code,
                        meta=meta,
                        fetched_at=now,
                        expires_at=expires_at,
                    )
                )
            updated += 1
        session.commit()

    print(f"cache refreshed: {updated} categories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
