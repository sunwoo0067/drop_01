import sys
import os
from app.db import SessionLocal
from app.models import APIKey

sys.path.append(os.getcwd())

def insert_test_key():
    db = SessionLocal()
    try:
        # Check if already exists
        exists = db.query(APIKey).filter_by(key="sk-test-db-key-123").first()
        if exists:
            print("Test key already exists")
            return

        new_key = APIKey(
            provider="openai",
            key="sk-test-db-key-123",
            is_active=True
        )
        db.add(new_key)
        db.commit()
        print("Inserted test OpenAI key: sk-test-db-key-123")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    insert_test_key()
