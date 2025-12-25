import logging
import uuid
import sys
from app.session_factory import session_factory
from app.models import MarketAccount, Product
from app.smartstore_sync import register_smartstore_product

logging.basicConfig(level=logging.INFO)

def test_reg():
    with session_factory() as session:
        # Get c네이버 account
        acc = session.query(MarketAccount).filter(MarketAccount.name == "c네이버").first()
        if not acc:
            print("Account c네이버 not found")
            return
        
        # Get specific product to test fallback
        product_id = "760187a1-debb-4a81-8893-f24a48925285"
        product = session.get(Product, uuid.UUID(product_id))
        if not product:
            print(f"Product {product_id} not found")
            return
            
        print(f"Testing registration for Product: {product.name} ({product.id})")
        print(f"To Account: {acc.name} ({acc.id})")
        
        res = register_smartstore_product(session, acc.id, product.id)
        print(f"Result: {res}")

if __name__ == "__main__":
    test_reg()
