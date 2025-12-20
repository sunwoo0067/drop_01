"""sourcing_candidates 유니크 제약 추가

Revision ID: 3a1f2c9e5d7b
Revises: b6a6cd68987c
Create Date: 2025-12-17 15:39:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "3a1f2c9e5d7b"
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
    op.create_unique_constraint(
        "uq_sourcing_candidates_supplier_item",
        "sourcing_candidates",
        ["supplier_code", "supplier_item_id"],
    )


def downgrade_dropship() -> None:
    op.drop_constraint(
        "uq_sourcing_candidates_supplier_item",
        "sourcing_candidates",
        type_="unique",
    )


def upgrade_market() -> None:
    pass


def downgrade_market() -> None:
    pass
