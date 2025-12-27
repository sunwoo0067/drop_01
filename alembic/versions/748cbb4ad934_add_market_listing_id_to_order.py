"""add_market_listing_id_to_order

Revision ID: 748cbb4ad934
Revises: add_product_lifecycle_strategy
Create Date: 2025-12-26 04:44:17.033166

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '748cbb4ad934'
down_revision: Union[str, None] = 'add_product_lifecycle_strategy'
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
    pass


def downgrade_market() -> None:
    pass
