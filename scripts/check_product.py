from app.session_factory import session_factory
from app.models import Product
from sqlalchemy import select

with session_factory() as session:
    p = session.execute(select(Product).order_by(Product.created_at.desc())).scalars().first()
    print(f"Product: {p.name}")
    print(f"Description: {p.description[:50] if p.description else 'None'}")
    print(f"Images: {p.processed_image_urls}")
