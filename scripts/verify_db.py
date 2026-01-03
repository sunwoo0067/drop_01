
from app.db import dropship_engine, market_engine, source_engine
from sqlalchemy import text

def verify():
    with dropship_engine.connect() as c:
        p = c.execute(text("SELECT count(*) FROM products")).scalar()
        po = c.execute(text("SELECT count(*) FROM product_options")).scalar()
        sc = c.execute(text("SELECT count(*) FROM sourcing_candidates")).scalar()
        print(f"Dropship DB -> Products: {p}, Options: {po}, Candidates: {sc}")

    with market_engine.connect() as c:
        ml = c.execute(text("SELECT count(*) FROM market_listings")).scalar()
        print(f"Market DB -> MarketListings: {ml}")

    with source_engine.connect() as c:
        raw = c.execute(text("SELECT count(*) FROM supplier_item_raw")).scalar()
        print(f"Source DB -> RawItems: {raw}")

if __name__ == "__main__":
    verify()
