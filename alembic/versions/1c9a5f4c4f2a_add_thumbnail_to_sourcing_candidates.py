"""add thumbnail url to sourcing candidates

Revision ID: 1c9a5f4c4f2a
Revises: b6a6cd68987c
Create Date: 2024-02-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1c9a5f4c4f2a"
down_revision: Union[str, None] = "b6a6cd68987c"
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
    op.add_column("sourcing_candidates", sa.Column("thumbnail_url", sa.Text(), nullable=True))


def downgrade_dropship() -> None:
    op.drop_column("sourcing_candidates", "thumbnail_url")


def upgrade_market() -> None:
    pass


def downgrade_market() -> None:
    pass
