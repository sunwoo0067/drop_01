"""add job progress columns

Revision ID: 47c14cfebd20
Revises: 1c9a5f4c4f2a
Create Date: 2024-02-15 00:00:00.000001

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "47c14cfebd20"
down_revision: Union[str, None] = "69e6b333ae6d"
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
    # Columns already added in 69e6b333ae6d; keep this migration as a no-op to avoid duplicate DDL.
    pass


def downgrade_market() -> None:
    pass
