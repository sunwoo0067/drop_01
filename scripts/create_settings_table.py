import uuid
from datetime import datetime
from sqlalchemy import create_engine, text
from app.settings import settings

engine = create_engine(settings.market_database_url)

with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS system_settings (
            id UUID PRIMARY KEY,
            key TEXT NOT NULL UNIQUE,
            value JSONB NOT NULL,
            description TEXT,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """))
    conn.commit()
    print("Table system_settings created or already exists.")
