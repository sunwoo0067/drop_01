from sqlalchemy.orm import Session

from app.db import SessionLocal


def session_factory() -> Session:
    return SessionLocal()
