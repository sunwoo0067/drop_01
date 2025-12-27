from app.session_factory import session_factory
from app.models import Product
from sqlalchemy import select, func

with session_factory() as session:
    stmt = select(Product.processing_status, func.count(Product.id)).group_by(Product.processing_status)
    results = session.execute(stmt).all()
    for status, count in results:
        print(f"Status {status}: {count}")
