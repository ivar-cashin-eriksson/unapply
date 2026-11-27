"""Add the candidates' consents: which jobs they opted in to, and what each may read.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.create_table(
        "consents",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_consents_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_consents_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("candidate_id", "job_id", name=op.f("pk_consents")),
    )
    with op.batch_alter_table("consents", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_consents_job_id"), ["job_id"], unique=False
        )


def downgrade() -> None:
    """Undo this migration."""
    with op.batch_alter_table("consents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_consents_job_id"))

    op.drop_table("consents")
