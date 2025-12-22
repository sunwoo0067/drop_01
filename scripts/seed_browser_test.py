import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import SessionLocal
from app.models import Product
import uuid


def seed_browser_product():
    """Ensure at least one browser-test product exists without running on import."""
    session = SessionLocal()
    try:
        existing = session.query(Product).first()
        if not existing:
            p = Product(
                id=uuid.uuid4(),
                name="Browser Test Product",
                status="DRAFT",
                processing_status="COMPLETED",
                selling_price=15000,
                cost_price=10000,
                description="<p>Test</p>",
            )
            session.add(p)
            session.commit()
            print("Inserted test product")
        else:
            print("Product already exists")
    finally:
        session.close()


if __name__ == "__main__":
    seed_browser_product()
