import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import uuid

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models import Product, MarketAccount, MarketListing
from app.coupang_sync import register_product

class TestCoupangRegistration(unittest.TestCase):
    def setUp(self):
        self.mock_session = MagicMock()
        self.mock_client = MagicMock()
        
    @patch('app.coupang_sync._get_client_for_account')
    def test_register_product_with_prediction(self, mock_get_client):
        # Setup mocks
        mock_get_client.return_value = self.mock_client
        
        # Mock API responses
        self.mock_client.get_outbound_shipping_centers.return_value = (200, {"data": {"content": [{"outboundShippingPlaceCode": "OUT123"}]}})
        self.mock_client.get_return_shipping_centers.return_value = (200, {"data": {"content": [{"returnCenterCode": "RET123"}]}})
        self.mock_client.create_product.return_value = (200, {"code": "SUCCESS", "data": "SUCCESS"})
        
        # Mock Predict Category
        self.mock_client.predict_category.return_value = (200, {"code": "SUCCESS", "data": {"predictedCategoryCode": "99999"}})

        # Mock Data
        account = MarketAccount(id=uuid.uuid4(), market_code="COUPANG", is_active=True, credentials={"vendor_id": "A001"})
        product = Product(
            id=uuid.uuid4(),
            name="Test Product",
            selling_price=10000,
            processed_name="Processed Test Product",
            description="<p>Desc</p>",
            status="ACTIVE"
        )
        
        self.mock_session.get.side_effect = lambda model, id: account if model == MarketAccount else product
        self.mock_session.scalars.return_value.first.return_value = None # No existing listing

        # Execute
        result = register_product(self.mock_session, account.id, product.id)
        
        # Verify
        self.assertTrue(result)
        self.mock_client.predict_category.assert_called_with("Processed Test Product")
        
        # Check if 99999 was used in create_product payload
        args, _ = self.mock_client.create_product.call_args
        payload = args[0]
        self.assertEqual(payload["displayCategoryCode"], 99999)
        print("Verified: predicted_category_code 99999 used in payload.")

if __name__ == '__main__':
    unittest.main()
