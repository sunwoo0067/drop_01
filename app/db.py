from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.settings import settings

from app.models import SourceBase, DropshipBase, MarketBase
from app.settings import settings

source_engine = create_engine(settings.source_database_url, pool_pre_ping=True)
dropship_engine = create_engine(settings.dropship_database_url, pool_pre_ping=True)
market_engine = create_engine(settings.market_database_url, pool_pre_ping=True)

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
        with session.begin():
            yield session
