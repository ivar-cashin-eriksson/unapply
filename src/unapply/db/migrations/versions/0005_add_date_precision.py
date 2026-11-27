"""Add how precisely experience dates are known: to the year or to the month.

Rows stored before this migration were all written as months, so they get "month".

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    with op.batch_alter_table("experiences", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "start_precision",
                sa.String(length=8),
                server_default="month",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "end_precision",
                sa.String(length=8),
                server_default="month",
                nullable=False,
            )
        )


def downgrade() -> None:
    """Undo this migration."""
    with op.batch_alter_table("experiences", schema=None) as batch_op:
        batch_op.drop_column("end_precision")
        batch_op.drop_column("start_precision")
