import unittest
from unittest.mock import MagicMock, patch, call
import sys
import os
import uuid
from sqlalchemy.orm import Session

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models import Product, MarketAccount, MarketListing
from app.coupang_sync import register_products_bulk

class TestCoupangBulkRegistration(unittest.TestCase):
    def setUp(self):
        self.mock_session = MagicMock(spec=Session)
        
    @patch('app.coupang_sync.register_product')
    def test_register_products_bulk_all_drafts(self, mock_register_single):
        # Setup Mocks
        account_id = uuid.uuid4()
        account = MarketAccount(id=account_id, market_code="COUPANG", name="Test Account", is_active=True)
        
        # 3 Draft Products, 1 already linked (should be skipped)
        p1 = Product(id=uuid.uuid4(), name="P1", status="DRAFT", processing_status="COMPLETED")
        p2 = Product(id=uuid.uuid4(), name="P2", status="DRAFT", processing_status="COMPLETED")
        p3 = Product(id=uuid.uuid4(), name="P3", status="DRAFT", processing_status="COMPLETED")
        
        products = [p1, p2, p3]
        
        # Mock Session behavior
        # 1. Get Account
        self.mock_session.get.side_effect = lambda model, pk: account if model == MarketAccount and pk == account_id else None
        
        # 2. Select candidates (return list)
        self.mock_session.scalars.return_value.all.return_value = products
        
        # 3. Check for existing listing
        # Let's say p2 is already linked
        def execute_side_effect(stmt):
            # This is a bit tricky to mock exact SQL objects, so we inspect the compiled string or just rely on simpler recursion
            # For simplicity, we assume the logic calls execute -> scalars -> first
            # We will use side_effect on the scalars().first() chain if possible, but execute returns a ResultProxy
            pass
            
        mock_result = MagicMock()
        self.mock_session.execute.return_value = mock_result
        # scalars().first() calls:
        # First call for P1 -> None
        # Second call for P2 -> MockListing
        # Third call for P3 -> None
        listing_p2 = MarketListing(id=uuid.uuid4(), market_item_id="12345")
        mock_result.scalars.return_value.first.side_effect = [None, listing_p2, None]

        # 4. register_product return values
        # P1 -> Success
        # P3 -> Fail
        mock_register_single.side_effect = [True, False] 

        # Execute
        stats = register_products_bulk(self.mock_session, account_id, None)
        
        # Verify
        print(f"Stats: {stats}")
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["success"], 1) # P1
        self.assertEqual(stats["failed"], 1)  # P3
        # P2 was skipped, so not counted in success/fail, but is part of total processed candidates? 
        # Logic says: total = len(products). Success increments, Failed increments. Skipped is implicit.
        # Wait, P2 skip loop continues. So stats: Total 3, Success 1 (P1), Failed 1 (P3).
        # Implicitly Skipped = Total - Success - Failed = 1 (P2).
        
        # Assert calls
        # Expected calls to register_single: P1 and P3. P2 skipped.
        calls = [call(self.mock_session, account_id, p1.id), call(self.mock_session, account_id, p3.id)]
        mock_register_single.assert_has_calls(calls)
        self.assertEqual(mock_register_single.call_count, 2)
        
        # Assert Status Updates
        # P1 should be ACTIVE
        self.assertEqual(p1.status, "ACTIVE")
        # P2 (skipped/linked) logic: if DRAFT -> ACTIVE.
        self.assertEqual(p2.status, "ACTIVE")
        # P3 (failed) -> DRAFT (unchanged by outer loop, logic might change in inner but assuming inner handles its own status if strictly defined, but here we only verify outer loop)
        self.assertEqual(p3.status, "DRAFT")

if __name__ == '__main__':
    unittest.main()
