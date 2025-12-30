"""add coupang eligibility to product

Revision ID: 9f2d1c77b8b0
Revises: 7c9c2e6c6b3a
Create Date: 2025-12-30 17:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9f2d1c77b8b0"
down_revision: Union[str, None] = "7c9c2e6c6b3a"
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
    pass


def downgrade_market() -> None:
    pass


def upgrade_dropship() -> None:
    op.add_column(
        "products",
        sa.Column("coupang_eligibility", sa.Text(), nullable=False, server_default="UNKNOWN"),
    )
    op.alter_column("products", "coupang_eligibility", server_default=None)


def downgrade_dropship() -> None:
    op.drop_column("products", "coupang_eligibility")
