
from app.db import source_engine, dropship_engine, market_engine
from sqlalchemy import text

def kill_sessions(engine, name):
    try:
        with engine.connect() as conn:
            print(f"--- Killing sessions on {name} ---")
            query = """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = current_database() AND pid <> pg_backend_pid();
            """
            conn.execute(text(query))
            conn.commit()
            print(f"Sessions on {name} killed.")
    except Exception as e:
        print(f"Error killing sessions on {name}: {e}")

if __name__ == "__main__":
    kill_sessions(source_engine, "SourceDB")
    kill_sessions(dropship_engine, "DropshipDB")
    kill_sessions(market_engine, "MarketDB")
