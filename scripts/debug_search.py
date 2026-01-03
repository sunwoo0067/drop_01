
import asyncio
import logging
from app.ownerclan_client import OwnerClanClient
from app.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("debug_search")

async def test_search():
    from app.db import SessionLocal
    from app.models import SupplierAccount
    from sqlalchemy import select
    db = SessionLocal()
    acc = db.execute(
        select(SupplierAccount).where(SupplierAccount.supplier_code == "ownerclan").where(SupplierAccount.is_active == True)
    ).scalars().first()
    db.close()

    client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
        access_token=acc.access_token if acc else None
    )
    keyword = "텀블러"
    logger.info(f"Testing search for: {keyword}")
    status, data = client.get_products(keyword=keyword, limit=5)
    logger.info(f"Status: {status}")
    items = data.get("items") or []
    if items:
        first_item = items[0]
        item_code = first_item.get("item_code")
        logger.info(f"Fetching details for first item: {item_code}")
        d_status, d_data = client.get_product(item_code)
        logger.info(f"Detail Status: {d_status}")
        logger.info(f"Detail Data: {d_data}")
    else:
        logger.warning("No items found to test details fetch.")

if __name__ == "__main__":
    asyncio.run(test_search())
