"""add job progress columns

Revision ID: 47c14cfebd20
Revises: 1c9a5f4c4f2a
Create Date: 2024-02-15 00:00:00.000001

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "47c14cfebd20"
down_revision: Union[str, None] = "1c9a5f4c4f2a"
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
    op.add_column("benchmark_collect_jobs", sa.Column("category_url", sa.Text(), nullable=True))
    op.add_column("benchmark_collect_jobs", sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("benchmark_collect_jobs", sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("benchmark_collect_jobs", "processed_count", server_default=None)
    op.alter_column("benchmark_collect_jobs", "total_count", server_default=None)


def downgrade_market() -> None:
    op.drop_column("benchmark_collect_jobs", "total_count")
    op.drop_column("benchmark_collect_jobs", "processed_count")
    op.drop_column("benchmark_collect_jobs", "category_url")
