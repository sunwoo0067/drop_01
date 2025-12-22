import asyncio
from app.session_factory import session_factory
from app.services.sourcing_service import SourcingService

async def test():
    with session_factory() as s:
        service = SourcingService(s)
        client = service._get_ownerclan_primary_client()
        print("Calling get_products for '겨울'...")
        status, data = client.get_products(keyword='겨울', limit=10)
        print(f"Status: {status}")
        items = service._extract_items(data)
        print(f"Count: {len(items)}")
        for it in items:
            name = it.get('item_name') or it.get('name')
            price = it.get('supply_price')
            print(f" - {name} (Price: {price})")

if __name__ == "__main__":
    asyncio.run(test())
