"""Add the candidates' progress on jobs (revealed, asked to apply, answered), and files.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.create_table(
        "job_progress",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("revealed_at", sa.DateTime(), nullable=True),
        sa.Column("revealed_profile_id", sa.Uuid(), nullable=True),
        sa.Column("charge", sa.JSON(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=True),
        sa.Column("answer", sa.String(length=16), nullable=True),
        sa.Column("answered_at", sa.DateTime(), nullable=True),
        sa.Column("letter", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_job_progress_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_job_progress_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("candidate_id", "job_id", name=op.f("pk_job_progress")),
    )
    with op.batch_alter_table("job_progress", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_job_progress_job_id"), ["job_id"], unique=False
        )

    op.create_table(
        "application_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id", "job_id"],
            ["job_progress.candidate_id", "job_progress.job_id"],
            name=op.f("fk_application_files_candidate_id_job_progress"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_files")),
    )
    with op.batch_alter_table("application_files", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_application_files_job_id"), ["job_id"], unique=False
        )


def downgrade() -> None:
    """Undo this migration."""
    with op.batch_alter_table("application_files", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_application_files_job_id"))

    op.drop_table("application_files")
    with op.batch_alter_table("job_progress", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_job_progress_job_id"))

    op.drop_table("job_progress")
