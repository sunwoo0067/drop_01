
from app.db import SessionLocal
from app.models import Product, ProductOption

db = SessionLocal()
try:
    products = db.query(Product).all()
    found = False
    for p in products:
        po_count = db.query(ProductOption).filter(ProductOption.product_id == p.id).count()
        if po_count > 1:
            print(f"FOUND: {p.name}, Options: {po_count}, ID: {p.id}")
            found = True
    
    if not found:
        print("No products with multiple options found.")
finally:
    db.close()
