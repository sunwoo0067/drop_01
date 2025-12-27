"""add_product_lifecycle_strategy

Revision ID: add_product_lifecycle_strategy
Revises: add_sales_analytics_tables
Create Date: 2025-12-25 15:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'add_product_lifecycle_strategy'
down_revision: Union[str, None] = 'add_sales_analytics_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade(engine_name: str = "") -> None:
    globals()[f"upgrade_{engine_name}"]()


def downgrade(engine_name: str = "") -> None:
    globals()[f"downgrade_{engine_name}"]()


def upgrade_source() -> None:
    # Add new columns to products table
    op.add_column('products', sa.Column('lifecycle_stage', sa.Text(), nullable=False, server_default='STEP_1', comment='STEP_1: 탐색, STEP_2: 검증, STEP_3: 스케일'))
    op.add_column('products', sa.Column('lifecycle_stage_updated_at', postgresql.TIMESTAMP(timezone=True), nullable=True, comment='단계 변경 시점'))
    op.add_column('products', sa.Column('total_sales_count', sa.Integer(), nullable=False, server_default='0', comment='총 판매 횟수'))
    op.add_column('products', sa.Column('total_views', sa.Integer(), nullable=False, server_default='0', comment='총 조회수'))
    op.add_column('products', sa.Column('total_clicks', sa.Integer(), nullable=False, server_default='0', comment='총 클릭수'))
    op.add_column('products', sa.Column('ctr', sa.Float(), nullable=False, server_default='0.0', comment='클릭률 (clicks / views)'))
    op.add_column('products', sa.Column('conversion_rate', sa.Float(), nullable=False, server_default='0.0', comment='전환율 (sales / clicks)'))
    op.add_column('products', sa.Column('repeat_purchase_count', sa.Integer(), nullable=False, server_default='0', comment='재구매 횟수'))
    op.add_column('products', sa.Column('option_expansion_count', sa.Integer(), nullable=False, server_default='0', comment='옵션 확장 횟수'))
    op.add_column('products', sa.Column('customer_retention_rate', sa.Float(), nullable=False, server_default='0.0', comment='고객 유지율'))
    op.add_column('products', sa.Column('total_revenue', sa.Integer(), nullable=False, server_default='0', comment='총 매출'))
    op.add_column('products', sa.Column('avg_customer_value', sa.Float(), nullable=False, server_default='0.0', comment='고객당 평균 가치'))
    op.add_column('products', sa.Column('last_processing_type', sa.Text(), nullable=True, comment='마지막 가공 유형 (NAME, OPTION, DESCRIPTION, IMAGE, DETAIL_PAGE)'))
    op.add_column('products', sa.Column('last_processing_at', postgresql.TIMESTAMP(timezone=True), nullable=True, comment='마지막 가공 시점'))
    op.add_column('products', sa.Column('ai_model_used', sa.Text(), nullable=True, comment='사용된 AI 모델 (qwen3:8b, qwen3-vl:8b, etc.)'))

    # Create product_lifecycles table
    op.create_table('product_lifecycles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('transition_sequence', sa.Integer(), nullable=False, server_default='1', comment='전환 순서 (1, 2, 3...)'),
        sa.Column('from_stage', sa.Text(), nullable=True, comment='이전 단계 (STEP_1, STEP_2, STEP_3)'),
        sa.Column('to_stage', sa.Text(), nullable=False, comment='새 단계 (STEP_1, STEP_2, STEP_3)'),
        sa.Column('kpi_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}', comment='전환 시점의 KPI 스냅샷'),
        sa.Column('transition_reason', sa.Text(), nullable=True, comment='단계 전환 사유'),
        sa.Column('auto_transition', sa.Boolean(), nullable=False, server_default='false', comment='자동 전환 여부'),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('product_lifecycles_product_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('product_lifecycles_pkey')),
        sa.UniqueConstraint('product_id', 'transition_sequence', name=op.f('uq_product_lifecycles_product_seq'))
    )

    # Create processing_histories table
    op.create_table('processing_histories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('processing_type', sa.Text(), nullable=False, comment='가공 유형 (NAME, OPTION, DESCRIPTION, IMAGE, DETAIL_PAGE, FULL_BRANDING)'),
        sa.Column('processing_stage', sa.Text(), nullable=False, comment='가공 시점의 단계 (STEP_1, STEP_2, STEP_3)'),
        sa.Column('before_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}', comment='가공 전 상태 (name, description, image_urls, etc.)'),
        sa.Column('before_kpi', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}', comment='가공 전 KPI (ctr, conversion_rate, etc.)'),
        sa.Column('after_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}', comment='가공 후 상태'),
        sa.Column('after_kpi', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='가공 후 KPI (일정 기간 후 업데이트)'),
        sa.Column('ai_model', sa.Text(), nullable=True, comment='사용된 AI 모델'),
        sa.Column('ai_processing_time_ms', sa.Integer(), nullable=True, comment='AI 처리 시간 (ms)'),
        sa.Column('ai_cost_estimate', sa.Float(), nullable=True, comment='추정 AI 처리 비용'),
        sa.Column('kpi_improvement', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='KPI 개선율 (ctr_change, conversion_change, etc.)'),
        sa.Column('roi_score', sa.Float(), nullable=True, comment='ROI 점수 (0-100)'),
        sa.Column('processed_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('kpi_measured_at', postgresql.TIMESTAMP(timezone=True), nullable=True, comment='가공 후 KPI 측정 시점'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('processing_histories_product_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('processing_histories_pkey'))
    )


def upgrade_dropship() -> None:
    pass


def upgrade_market() -> None:
    # Add new columns to market_listings table
    op.add_column('market_listings', sa.Column('view_count', sa.Integer(), nullable=False, server_default='0', comment='노출수'))
    op.add_column('market_listings', sa.Column('click_count', sa.Integer(), nullable=False, server_default='0', comment='클릭수'))
    op.add_column('market_listings', sa.Column('kpi_updated_at', postgresql.TIMESTAMP(timezone=True), nullable=True, comment='KPI 마지막 업데이트 시점'))


def downgrade_source() -> None:
    # Drop tables
    op.drop_table('processing_histories')
    op.drop_table('product_lifecycles')

    # Drop columns from products
    op.drop_column('products', 'ai_model_used')
    op.drop_column('products', 'last_processing_at')
    op.drop_column('products', 'last_processing_type')
    op.drop_column('products', 'avg_customer_value')
    op.drop_column('products', 'total_revenue')
    op.drop_column('products', 'customer_retention_rate')
    op.drop_column('products', 'option_expansion_count')
    op.drop_column('products', 'repeat_purchase_count')
    op.drop_column('products', 'conversion_rate')
    op.drop_column('products', 'ctr')
    op.drop_column('products', 'total_clicks')
    op.drop_column('products', 'total_views')
    op.drop_column('products', 'total_sales_count')
    op.drop_column('products', 'lifecycle_stage_updated_at')
    op.drop_column('products', 'lifecycle_stage')


def downgrade_dropship() -> None:
    # Drop tables
    op.drop_table('processing_histories')
    op.drop_table('product_lifecycles')

    # Drop columns from products
    op.drop_column('products', 'ai_model_used')
    op.drop_column('products', 'last_processing_at')
    op.drop_column('products', 'last_processing_type')
    op.drop_column('products', 'avg_customer_value')
    op.drop_column('products', 'total_revenue')
    op.drop_column('products', 'customer_retention_rate')
    op.drop_column('products', 'option_expansion_count')
    op.drop_column('products', 'repeat_purchase_count')
    op.drop_column('products', 'conversion_rate')
    op.drop_column('products', 'ctr')
    op.drop_column('products', 'total_clicks')
    op.drop_column('products', 'total_views')
    op.drop_column('products', 'total_sales_count')
    op.drop_column('products', 'lifecycle_stage_updated_at')
    op.drop_column('products', 'lifecycle_stage')


def downgrade_market() -> None:
    # Drop columns from market_listings
    op.drop_column('market_listings', 'kpi_updated_at')
    op.drop_column('market_listings', 'click_count')
    op.drop_column('market_listings', 'view_count')
