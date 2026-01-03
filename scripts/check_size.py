
from app.db import source_engine
from sqlalchemy import text

with source_engine.connect() as conn:
    count = conn.execute(text("SELECT count(*) FROM supplier_item_raw")).scalar()
    print(f"Raw items count: {count}")
