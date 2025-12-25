"""Add sales analytics and sourcing recommendation tables

Revision ID: add_sales_analytics_tables
Revises: 7513fb14f010
Create Date: 2025-12-25 13:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy

revision: str = 'add_sales_analytics_tables'
down_revision: Union[str, None] = '7513fb14f010'
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
    # Create sales_analytics table
    op.create_table(
        'sales_analytics',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('product_id', sa.UUID(), nullable=False),
        sa.Column('period_type', sa.Text(), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('total_orders', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_revenue', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_profit', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_margin_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('order_growth_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('revenue_growth_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('predicted_orders', sa.Integer(), nullable=True),
        sa.Column('predicted_revenue', sa.Integer(), nullable=True),
        sa.Column('prediction_confidence', sa.Float(), nullable=True),
        sa.Column('category_trend_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('market_demand_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('trend_analysis', sa.Text(), nullable=True),
        sa.Column('insights', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('recommendations', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('analysis_version', sa.Text(), nullable=False, server_default='v1.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.UniqueConstraint('product_id', 'period_type', 'period_start', name='uq_sales_analytics_product_period')
    )

    # Create sourcing_recommendations table
    op.create_table(
        'sourcing_recommendations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('product_id', sa.UUID(), nullable=True),
        sa.Column('supplier_item_id', sa.UUID(), nullable=True),
        sa.Column('recommendation_type', sa.Text(), nullable=False),
        sa.Column('recommendation_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('overall_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('sales_potential_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('market_trend_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('profit_margin_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('supplier_reliability_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('seasonal_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('recommended_quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('min_quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('current_supply_price', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('recommended_selling_price', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expected_margin', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('current_stock', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('stock_days_left', sa.Integer(), nullable=True),
        sa.Column('reorder_point', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('risk_factors', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('opportunity_factors', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default='PENDING'),
        sa.Column('action_taken', sa.Text(), nullable=True),
        sa.Column('model_version', sa.Text(), nullable=False, server_default='v1.0'),
        sa.Column('confidence_level', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.UniqueConstraint('product_id', 'recommendation_date', name='uq_sourcing_recommendations_product_date')
    )

    # Create supplier_performance table
    op.create_table(
        'supplier_performance',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('supplier_code', sa.Text(), nullable=False),
        sa.Column('period_type', sa.Text(), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('total_orders', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('successful_orders', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_orders', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('order_success_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('avg_delivery_time_hours', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('on_time_delivery_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('late_delivery_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('return_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('complaint_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('avg_product_rating', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('avg_price_competitiveness', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('overall_reliability_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('supplier_code', 'period_type', 'period_start', name='uq_supplier_performance_supplier_period')
    )


def downgrade_dropship() -> None:
    # Drop tables in reverse order
    op.drop_table('supplier_performance')
    op.drop_table('sourcing_recommendations')
    op.drop_table('sales_analytics')
