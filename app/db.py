from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.settings import settings

from app.models import SourceBase, DropshipBase, MarketBase


source_engine = create_engine(settings.source_database_url, pool_pre_ping=True, pool_size=20, max_overflow=20)
dropship_engine = create_engine(settings.dropship_database_url, pool_pre_ping=True, pool_size=20, max_overflow=20)
market_engine = create_engine(settings.market_database_url, pool_pre_ping=True, pool_size=20, max_overflow=20)

SessionLocal = sessionmaker(
    autoflush=False,
    expire_on_commit=False,
    binds={
        SourceBase: source_engine,
        DropshipBase: dropship_engine,
        MarketBase: market_engine,
    },
)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
