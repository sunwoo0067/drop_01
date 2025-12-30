"""add coupang policy fields

Revision ID: 86f42d1595e3
Revises: f3dfc67b9b8b
Create Date: 2025-12-30 13:55:04.053217

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '86f42d1595e3'
down_revision: Union[str, None] = 'f3dfc67b9b8b'
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
        "coupang_document_library",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=False),
        sa.Column("template_name", sa.Text(), nullable=False),
        sa.Column("vendor_document_path", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand", "template_name", name="uq_coupang_document_library_brand_template"),
    )
    op.create_table(
        "coupang_brand_policies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=False),
        sa.Column("naver_fallback_disabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand", name="uq_coupang_brand_policies_brand"),
    )
    op.create_table(
        "market_registration_retries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("market_code", sa.Text(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("queued"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_code", "product_id", name="uq_market_registration_retries_market_product"),
    )


def downgrade_market() -> None:
    op.drop_table("market_registration_retries")
    op.drop_table("coupang_brand_policies")
    op.drop_table("coupang_document_library")


def upgrade_dropship() -> None:
    op.add_column(
        "products",
        sa.Column("coupang_parallel_imported", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "products",
        sa.Column("coupang_overseas_purchased", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "products",
        sa.Column("naver_fallback_disabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "products",
        sa.Column("coupang_doc_pending", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "products",
        sa.Column("coupang_doc_pending_reason", sa.Text(), nullable=True),
    )


def downgrade_dropship() -> None:
    op.drop_column("products", "coupang_doc_pending_reason")
    op.drop_column("products", "coupang_doc_pending")
    op.drop_column("products", "naver_fallback_disabled")
    op.drop_column("products", "coupang_overseas_purchased")
    op.drop_column("products", "coupang_parallel_imported")
