"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade(engine_name: str = "") -> None:
    globals()[f"upgrade_{engine_name}"]()


def downgrade(engine_name: str = "") -> None:
    globals()[f"downgrade_{engine_name}"]()


def upgrade_source() -> None:
    ${source_upgrades if source_upgrades else "pass"}


def downgrade_source() -> None:
    ${source_downgrades if source_downgrades else "pass"}


def upgrade_dropship() -> None:
    ${dropship_upgrades if dropship_upgrades else "pass"}


def downgrade_dropship() -> None:
    ${dropship_downgrades if dropship_downgrades else "pass"}


def upgrade_market() -> None:
    ${market_upgrades if market_upgrades else "pass"}


def downgrade_market() -> None:
    ${market_downgrades if market_downgrades else "pass"}
