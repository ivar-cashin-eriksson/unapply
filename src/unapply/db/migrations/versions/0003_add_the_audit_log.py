"""Add the audit log: an append-only record of every match and ranking.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("rubric_version", sa.Integer(), nullable=False),
        sa.Column("rubric_hash", sa.String(length=80), nullable=False),
        sa.Column("scorer", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=True),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("profile_hash", sa.String(length=80), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    with op.batch_alter_table("audit_log", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_audit_log_job_id"), ["job_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_audit_log_match_id"), ["match_id"], unique=False
        )


def downgrade() -> None:
    """Undo this migration."""
    with op.batch_alter_table("audit_log", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_log_match_id"))
        batch_op.drop_index(batch_op.f("ix_audit_log_job_id"))

    op.drop_table("audit_log")
