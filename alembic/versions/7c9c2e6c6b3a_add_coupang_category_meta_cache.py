"""add coupang category meta cache

Revision ID: 7c9c2e6c6b3a
Revises: 86f42d1595e3
Create Date: 2025-12-30 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '7c9c2e6c6b3a'
down_revision: Union[str, None] = '86f42d1595e3'
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


def upgrade_market() -> None:
    op.create_table(
        "coupang_category_meta_cache",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("category_code", sa.Text(), nullable=False),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_code", name="uq_coupang_category_meta_cache_category_code"),
    )


def downgrade_market() -> None:
    op.drop_table("coupang_category_meta_cache")


def upgrade_dropship() -> None:
    pass


def downgrade_dropship() -> None:
    pass
