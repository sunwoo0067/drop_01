"""add_benchmark_collect_jobs_table

Revision ID: 2a6b1f4c9e10
Revises: d5efd4eb83f9
Create Date: 2025-12-16

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "2a6b1f4c9e10"
down_revision: Union[str, None] = "d5efd4eb83f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "benchmark_collect_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("market_code", sa.Text(), nullable=False, server_default="COUPANG"),
        sa.Column("markets", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("limit", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_markets", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("benchmark_collect_jobs")
