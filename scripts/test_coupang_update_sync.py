import unittest
from unittest.mock import MagicMock, patch
import uuid
import os
from app.coupang_sync import update_product_on_coupang
from app.models import Product, MarketListing, MarketAccount

class TestCoupangUpdateSync(unittest.TestCase):
    @patch('app.coupang_sync._get_client_for_account')
    @patch('app.coupang_sync._get_default_centers')
    def test_update_product_on_coupang_full_sync(self, mock_get_centers, mock_get_client):
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
        
        # Mock _get_default_centers
        mock_get_centers.return_value = ("RET_CODE", "OUT_CODE", "KDEXP", "debug")
        
        # Mock API responses within _get_coupang_product_metadata
        mock_client.check_auto_category_agreed.return_value = (200, {"code": "SUCCESS", "data": True})
        mock_client.predict_category.return_value = (200, {"code": "SUCCESS", "data": {"predictedCategoryCode": "77800"}})
        mock_client.get_category_meta.return_value = (200, {"code": "SUCCESS", "data": {}})
        mock_client.get_return_shipping_center_by_code.return_value = (200, {"code": "SUCCESS", "data": []})
        
        # Mock update_product response
        mock_client.update_product.return_value = (200, {"code": "SUCCESS"})
        
        # Enable category prediction for test
        with patch.dict(os.environ, {"COUPANG_ENABLE_CATEGORY_PREDICTION": "1"}):
            # Execute
            ok, error = update_product_on_coupang(session, account_id, product_id)
        
        # Verify
        self.assertTrue(ok)
        self.assertIsNone(error)
        
        # Check if update_product was called
        self.assertTrue(mock_client.update_product.called)
        called_payload = mock_client.update_product.call_args[0][0]
        
        # Check Full Sync payload contents
        self.assertEqual(called_payload["displayProductName"], "Processed Name")
        self.assertEqual(called_payload["sellerProductName"], "Processed Name")
        self.assertEqual(called_payload["displayCategoryCode"], 77800)
        self.assertEqual(called_payload["returnCenterCode"], "RET_CODE")
        self.assertEqual(called_payload["outboundShippingPlaceCode"], "OUT_CODE")
        
        # Check Item level
        item = called_payload["items"][0]
        self.assertEqual(item["salePrice"], 10000)
        self.assertEqual(item["originalPrice"], 10000)
        self.assertEqual(len(item["images"]), 2)
        self.assertEqual(len(item["contents"]), 2) # image blocks

if __name__ == '__main__':
    unittest.main()
