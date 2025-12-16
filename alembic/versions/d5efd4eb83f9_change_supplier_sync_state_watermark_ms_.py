"""supplier_sync_state.watermark_ms 컬럼을 bigint로 변경

Revision ID: d5efd4eb83f9
Revises: f3779c243ce9
Create Date: 2025-12-16 12:05:15.535654

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd5efd4eb83f9'
down_revision: Union[str, None] = 'f3779c243ce9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # watermark_ms는 epoch milliseconds(13자리)를 저장하므로 INTEGER 오버플로우가 발생할 수 있어 BIGINT로 변경합니다.
    op.alter_column(
        "supplier_sync_state",
        "watermark_ms",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "supplier_sync_state",
        "watermark_ms",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
