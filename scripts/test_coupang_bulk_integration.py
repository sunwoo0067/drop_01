import sys
import os
import uuid
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.db import get_session, SessionLocal, dropship_engine
from app.models import Product, MarketAccount, MarketListing

# Use an in-memory SQLite db for speed and isolation, OR use the dev DB if we want to confirm real postgres behavior (using pgvector etc).
# Since we are using postgres specific features (pgvector, insert.on_conflict_do_update), sqlite might fail if we use those dialects.
# Let's try to trust the mocking of the DB session for the *endpoint* but that defeats the purpose of "integration".
# So we will use the app's `get_session` but we will mock the COUPANG CLIENT.

client = TestClient(app)

def test_bulk_registration_integration():
    # 1. Mock Coupang Client to avoid real API calls
    with patch('app.coupang_sync.CoupangClient') as MockClientClass:
        mock_instance = MockClientClass.return_value
        # Mock create_product to return success (HTTP 200, code=SUCCESS, data=ID)
        mock_instance.create_product.return_value = (200, {"code": "SUCCESS", "data": 999999})
        
        # Mock get_category_tree if called
        mock_instance.get_category_tree.return_value = (200, {"data": []})
        
        # Mock get_outbound/return shipping centers
        mock_instance.get_outbound_shipping_centers.return_value = (200, {"data": {"content": [{"outboundShippingPlaceCode": "OUT123"}]}})
        mock_instance.get_return_shipping_centers.return_value = (200, {"data": {"content": [{"returnCenterCode": "RET123"}]}})
        
        # Mock predict_category (HTTP 200, code=SUCCESS, data dict with predictedCategoryCode)
        mock_instance.predict_category.return_value = (200, {"code": "SUCCESS", "data": {"predictedCategoryCode": 77800}})
        
        # 2. Insert Test Data into the REAL DB (Assumption: Dev DB is available)
        # We need to manually create a session to setup data
        # SessionLocal is already imported
        session = SessionLocal()
        
        # Create a test account if not exists
        account = session.query(MarketAccount).filter_by(market_code="COUPANG").first()
        if not account:
            account = MarketAccount(id=uuid.uuid4(), market_code="COUPANG", name="Test Account", is_active=True)
            session.add(account)
            session.commit()
            
        # Create test products
        p1_id = uuid.uuid4()
        p1 = Product(
            id=p1_id, 
            name="Integration Test Product 1", 
            status="DRAFT", 
            processing_status="COMPLETED",
            selling_price=10000,
            cost_price=5000
        )
        session.add(p1)
        session.commit()
        
        try:
            # 3. Call the API Endpoint
            response = client.post("/api/coupang/register/bulk", json={"productIds": [str(p1_id)]})
            print("API Response:", response.json())
            assert response.status_code == 202
            
            # 4. Wait/Poll for Background Task (TestClient acts sync for background tasks typically? 
            # Actually TestClient DOES run background tasks. )
            
            # 5. Verify DB State
            session.refresh(p1)
            print(f"Product Status: {p1.status}")
            
            if p1.status == "ACTIVE":
                print("SUCCESS: Product status updated to ACTIVE")
            else:
                print(f"FAILURE: Product status is {p1.status}")
                # Debug: why failed? Maybe background task didn't run or exception?
                # In TestClient, background tasks ARE executed. using Starlette's TestClient.
                
            # Verify MarketListing created
            listing = session.query(MarketListing).filter_by(product_id=p1_id).first()
            if listing:
                print(f"SUCCESS: MarketListing found: {listing.market_item_id}")
            else:
                print("FAILURE: MarketListing not found")
                
        finally:
            # Cleanup
            session.delete(p1)
            # Find and delete listing if exists (cascade might not be set)
            if 'listing' in locals() and listing:
                session.delete(listing)
            session.commit()
            session.close()

if __name__ == "__main__":
    test_bulk_registration_integration()
