from app.session_factory import session_factory
from app.models import Product
from sqlalchemy import select

with session_factory() as session:
    # Find a product that has an image URL containing speedgabia (OwnerClan)
    products = session.execute(select(Product)).scalars().all()
    found = False
    for p in products:
        if p.processed_image_urls:
            for url in p.processed_image_urls:
                if "speedgabia" in url.lower() or "ownerclan" in url.lower():
                    print(f"ID: {p.id}")
                    print(f"Name: {p.name}")
                    print(f"Image: {url}")
                    found = True
                    break
        if found: break
    if not found:
        print("No OwnerClan product with images found.")
