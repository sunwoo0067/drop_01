import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.db import get_session
from app.models import MarketAccount, MarketListing, Product
from sqlalchemy import select

client = TestClient(app)

def test_deletion_with_listings():
    # 1. Setup: Create account, product, and listing
    with next(get_session()) as session:
        acc = MarketAccount(
            market_code="COUPANG",
            name="TEST_DELETE_WITH_LISTINGS",
            credentials={"vendor_id": "TEST", "vendor_user_id": "TEST", "access_key": "TEST", "secret_key": "TEST"},
            is_active=False
        )
        session.add(acc)
        session.flush()
        
        prod = Product(name="TEST_PRODUCT", cost_price=1000, selling_price=2000)
        session.add(prod)
        session.commit() # Product를 먼저 커밋해야 MarketListing에서 참조 가능 (엔진 분리 때문)
        
    with next(get_session()) as session:
        acc = MarketAccount(
            market_code="COUPANG",
            name="TEST_DELETE_WITH_LISTINGS_" + uuid.uuid4().hex[:8],
            credentials={"vendor_id": "TEST", "vendor_user_id": "TEST", "access_key": "TEST", "secret_key": "TEST"},
            is_active=False
        )
        session.add(acc)
        session.flush()

        listing = MarketListing(
            product_id=prod.id,
            market_account_id=acc.id,
            market_item_id="TEST_ITEM_ID_" + uuid.uuid4().hex[:8]
        )
        session.add(listing)
        session.commit()
        
        acc_id = str(acc.id)
        listing_id = str(listing.id)
        print(f"Setup Complete: Account {acc_id}, Listing {listing_id}")

    # 2. Call the delete API
    response = client.delete(f"/api/settings/markets/coupang/accounts/{acc_id}")
    print(f"Delete API Response: {response.status_code}, {response.json()}")
    assert response.status_code == 200

    # 3. Verify cleanup
    with next(get_session()) as session:
        # Account should be gone
        acc_exists = session.get(MarketAccount, uuid.UUID(acc_id))
        # Listing should be gone
        listing_exists = session.get(MarketListing, uuid.UUID(listing_id))
        
        print(f"Account exists: {acc_exists is not None}")
        print(f"Listing exists: {listing_exists is not None}")
        
        if acc_exists is None and listing_exists is None:
            print("Verification Success: Account and associated Listing are deleted.")
        else:
            print("Verification Failure.")

if __name__ == "__main__":
    test_deletion_with_listings()
