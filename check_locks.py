
from app.db import source_engine, dropship_engine, market_engine
from sqlalchemy import text

def check_locks(engine, name):
    try:
        with engine.connect() as conn:
            print(f"--- Locks on {name} ---")
            query = """
            SELECT pid, state, query, wait_event_type, wait_event
            FROM pg_stat_activity
            WHERE datname = current_database() AND pid <> pg_backend_pid();
            """
            result = conn.execute(text(query)).fetchall()
            for row in result:
                print(row)
    except Exception as e:
        print(f"Error checking {name}: {e}")

if __name__ == "__main__":
    check_locks(source_engine, "SourceDB")
    check_locks(dropship_engine, "DropshipDB")
    check_locks(market_engine, "MarketDB")
