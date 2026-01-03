from app.db import source_engine, dropship_engine, market_engine
from sqlalchemy import text

def cleanup():
    # 1. Source DB
    with source_engine.connect() as conn:
        print("Truncating Source DB: supplier_item_raw")
        conn.execute(text("TRUNCATE TABLE supplier_item_raw CASCADE"))
        conn.commit()

    # 2. Dropship DB
    with dropship_engine.connect() as conn:
        for t in ["product_options", "products", "sourcing_candidates"]:
            print(f"Truncating Dropship DB: {t}")
            conn.execute(text(f"TRUNCATE TABLE {t} CASCADE"))
            conn.commit()

    # 3. Market DB
    with market_engine.connect() as conn:
        for t in ["market_listings", "market_product_raw"]:
            print(f"Truncating Market DB: {t}")
            conn.execute(text(f"TRUNCATE TABLE {t} CASCADE"))
            conn.commit()

    print("Cleanup successful.")

if __name__ == "__main__":
    cleanup()
