
from sqlalchemy import create_engine, text
from app.settings import settings

engine = create_engine(settings.market_database_url)

def check_db_schema():
    print("--- Checking market_accounts table schema ---")
    with engine.connect() as conn:
        # Get indexes
        print("\n[Indexes]")
        res = conn.execute(text("""
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE tablename = 'market_accounts';
        """))
        for row in res:
            print(f"- {row.indexname}: {row.indexdef}")

        # Get constraints
        print("\n[Constraints]")
        res = conn.execute(text("""
            SELECT conname, pg_get_constraintdef(oid) 
            FROM pg_constraint 
            WHERE conrelid = 'market_accounts'::regclass;
        """))
        for row in res:
            print(f"- {row.conname}: {row.pg_get_constraintdef}")

if __name__ == "__main__":
    check_db_schema()
