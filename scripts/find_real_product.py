from app.session_factory import session_factory
from app.models import Product
from sqlalchemy import select, func

with session_factory() as session:
    # Find a product that has at least one image URL
    # Using raw SQL if needed, but let's try python side filtering for simple cases
    products = session.execute(select(Product)).scalars().all()
    found = False
    for p in products:
        if p.processed_image_urls and len(p.processed_image_urls) > 0:
            print(f"ID: {p.id}")
            print(f"Name: {p.name}")
            print(f"Image: {p.processed_image_urls[0]}")
            found = True
            break
    if not found:
        print("No product with images found.")
