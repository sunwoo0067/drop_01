
import os
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool, create_engine

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.models import SourceBase, DropshipBase, MarketBase
import app.models_analytics
from app.settings import settings

# Mapping of database name to (Metadata, URL)
db_info = {
    "source": {"metadata": SourceBase.metadata, "url": settings.source_database_url},
    "dropship": {"metadata": DropshipBase.metadata, "url": settings.dropship_database_url},
    "market": {"metadata": MarketBase.metadata, "url": settings.market_database_url},
}

config = context.config


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode for all configured databases."""
    # This offline mode implementation iterates over all dbs.
    # To run for a specific db, one might need CLI args, but here we run all.
    
    for name, info in db_info.items():
        def include_object(object, name, type_, reflected, compare_to):
            if type_ == "table":
                return name in info["metadata"].tables
            return True

        context.configure(
            url=info["url"],
            target_metadata=info["metadata"],
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            version_table=f"alembic_version_{name}", # Separate version table per DB
            upgrade_token=f"{name}_upgrades",
            downgrade_token=f"{name}_downgrades",
            include_object=include_object,
        )
        
        with context.begin_transaction():
            context.run_migrations(engine_name=name)


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    
    # We will create engines manually from settings, ignoring .ini urls for simplicity
    # or we can read from .ini if we populated them. Using settings is safer/consistent.

    for name, info in db_info.items():
        engine = create_engine(info["url"], poolclass=pool.NullPool)

        with engine.connect() as connection:
            def include_object(object, name, type_, reflected, compare_to):
                if type_ == "table":
                    return name in info["metadata"].tables
                return True

            context.configure(
                connection=connection,
                target_metadata=info["metadata"],
                version_table=f"alembic_version_{name}", # Separate version table per DB
                upgrade_token=f"{name}_upgrades",
                downgrade_token=f"{name}_downgrades",
                include_object=include_object,
            )

            with context.begin_transaction():
                context.run_migrations(engine_name=name)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
