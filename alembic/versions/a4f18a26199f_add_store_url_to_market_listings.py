"""add store_url to market_listings

Revision ID: a4f18a26199f
Revises: 748cbb4ad934
Create Date: 2025-12-27 16:11:38.167441

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a4f18a26199f'
down_revision: Union[str, None] = '748cbb4ad934'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str = "") -> None:
    globals()[f"upgrade_{engine_name}"]()


def downgrade(engine_name: str = "") -> None:
    globals()[f"downgrade_{engine_name}"]()


def upgrade_source() -> None:
    pass


def downgrade_source() -> None:
    pass


def upgrade_dropship() -> None:
    pass


def downgrade_dropship() -> None:
    pass


def upgrade_market() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {col["name"] for col in inspector.get_columns("market_listings")}
    if "store_url" not in existing_cols:
        op.add_column("market_listings", sa.Column("store_url", sa.Text(), nullable=True))


def downgrade_market() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {col["name"] for col in inspector.get_columns("market_listings")}
    if "store_url" in existing_cols:
        op.drop_column("market_listings", "store_url")
