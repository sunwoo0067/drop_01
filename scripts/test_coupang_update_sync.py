import unittest
from unittest.mock import MagicMock, patch
import uuid
from app.coupang_sync import update_product_on_coupang
from app.models import Product, MarketListing, MarketAccount

class TestCoupangUpdateSync(unittest.TestCase):
    @patch('app.coupang_sync._get_client_for_account')
    def test_update_product_on_coupang_syncs_local_data(self, mock_get_client):
        # Setup
        session = MagicMock()
        account_id = uuid.uuid4()
        product_id = uuid.uuid4()
        
        account = MarketAccount(id=account_id, market_code="COUPANG", credentials={"vendor_id": "V123"})
        product = Product(
            id=product_id, 
            name="Original Name", 
            processed_name="Processed Name",
            selling_price=10000,
            processed_image_urls=["http://image1.jpg", "http://image2.jpg"],
            description="Local Description"
        )
        listing = MarketListing(market_account_id=account_id, product_id=product_id, market_item_id="12345")
        
        session.get.side_effect = lambda model, id: {
            MarketAccount: account,
            Product: product
        }.get(model)
        
        mock_result = MagicMock()
        mock_result.scalars().first.return_value = listing
        session.execute.return_value = mock_result
        
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        # Mock Coupang GET response
        current_data = {
            "code": "SUCCESS",
            "data": {
                "sellerProductId": 12345,
                "displayCategoryCode": 77800,
                "items": [{
                    "vendorItemId": 54321,
                    "salePrice": 5000,
                    "originalPrice": 5000,
                    "images": [{"vendorPath": "old_url"}]
                }]
            }
        }
        mock_client.get_product.return_value = (200, current_data)
        mock_client.update_product.return_value = (200, {"code": "SUCCESS"})
        
        # Execute
        ok, error = update_product_on_coupang(session, account_id, product_id)
        
        # Verify
        self.assertTrue(ok)
        self.assertIsNone(error)
        
        # Check if update_product was called with correct payload
        called_payload = mock_client.update_product.call_args[0][0]
        
        # 1. Check Product Name
        self.assertEqual(called_payload["displayProductName"], "Processed Name")
        self.assertEqual(called_payload["sellerProductName"], "Processed Name")
        
        # 2. Check Price (selling_price=10000)
        # Note: shipping_fee is mocked as 0 because product.supplier_item_id is None
        self.assertEqual(called_payload["items"][0]["salePrice"], 10000)
        self.assertEqual(called_payload["items"][0]["originalPrice"], 10000) # Check originalPrice sync
        
        # 3. Check Images
        self.assertEqual(len(called_payload["items"][0]["images"]), 2)
        self.assertEqual(called_payload["items"][0]["images"][0]["vendorPath"], "http://image1.jpg")
        
        # 4. Check Contents
        self.assertTrue("contents" in called_payload["items"][0])
        self.assertEqual(len(called_payload["items"][0]["contents"]), 2) # 2 images -> 2 blocks

if __name__ == '__main__':
    unittest.main()
