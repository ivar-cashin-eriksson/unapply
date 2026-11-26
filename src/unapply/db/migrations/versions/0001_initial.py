"""Create the initial tables: candidates, profiles, jobs, rubrics and matches.

Revision ID: 0001
Revises:
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.create_table(
        "candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("approved_by_candidate_at", sa.DateTime(), nullable=True),
        sa.Column("locations", sa.JSON(), nullable=False),
        sa.Column("work_modes", sa.JSON(), nullable=False),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(length=3), nullable=True),
        sa.Column("work_permits", sa.JSON(), nullable=False),
        sa.Column("dealbreakers", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidates")),
        sa.UniqueConstraint("name", name=op.f("uq_candidates_name")),
        sa.UniqueConstraint("profile_id", name=op.f("uq_candidates_profile_id")),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("ad_text", sa.Text(), nullable=True),
        sa.Column("reveal_quota", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("rubric_version", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("job_id", name=op.f("uq_jobs_job_id")),
        sa.UniqueConstraint("name", name=op.f("uq_jobs_name")),
    )
    op.create_table(
        "candidate_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("step", sa.String(length=64), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("saved_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_candidate_history_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_history")),
    )
    with op.batch_alter_table("candidate_history", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_candidate_history_candidate_id"),
            ["candidate_id"],
            unique=False,
        )

    op.create_table(
        "candidate_skills",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.Column("self_level", sa.Integer(), nullable=True),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("estimate_level", sa.Integer(), nullable=True),
        sa.Column("estimate_confidence", sa.Float(), nullable=True),
        sa.Column("estimate_rationale", sa.Text(), nullable=True),
        sa.Column("estimate_evidence_ids", sa.JSON(), nullable=True),
        sa.Column("estimate_model", sa.String(length=200), nullable=True),
        sa.Column("estimated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_candidate_skills_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "candidate_id", "name", name=op.f("pk_candidate_skills")
        ),
    )
    op.create_table(
        "claim_support",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("rated", sa.Integer(), nullable=False),
        sa.Column("overclaims", sa.JSON(), nullable=False),
        sa.Column("underclaims", sa.JSON(), nullable=False),
        sa.Column("unverified", sa.JSON(), nullable=False),
        sa.Column("unsupported_claims", sa.JSON(), nullable=False),
        sa.Column("inconsistencies", sa.JSON(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_claim_support_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("candidate_id", name=op.f("pk_claim_support")),
    )
    op.create_table(
        "experiences",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("organisation", sa.Text(), nullable=False),
        sa.Column("start", sa.Date(), nullable=True),
        sa.Column("end", sa.Date(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_experiences_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("candidate_id", "id", name=op.f("pk_experiences")),
    )
    op.create_table(
        "interview_questions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("skill", sa.String(length=200), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("asked_at", sa.DateTime(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("answered_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_interview_questions_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interview_questions")),
    )
    with op.batch_alter_table("interview_questions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_interview_questions_candidate_id"),
            ["candidate_id"],
            unique=False,
        )

    op.create_table(
        "job_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("step", sa.String(length=64), nullable=False),
        sa.Column("job", sa.JSON(), nullable=False),
        sa.Column("saved_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_job_history_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_history")),
    )
    with op.batch_alter_table("job_history", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_job_history_job_id"), ["job_id"], unique=False
        )

    op.create_table(
        "rubric_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("hard_filters", sa.JSON(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_rubric_versions_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubric_versions")),
        sa.UniqueConstraint(
            "job_id", "version", name=op.f("uq_rubric_versions_job_id")
        ),
    )
    op.create_table(
        "sources",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("uri", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_sources_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("candidate_id", "id", name=op.f("pk_sources")),
    )
    op.create_table(
        "criteria",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rubric_version_id", sa.Integer(), nullable=False),
        sa.Column("criterion_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("skill", sa.String(length=200), nullable=True),
        sa.Column("min_level", sa.Integer(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("source_quote", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["rubric_version_id"],
            ["rubric_versions.id"],
            name=op.f("fk_criteria_rubric_version_id_rubric_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_criteria")),
        sa.UniqueConstraint(
            "rubric_version_id",
            "criterion_id",
            name=op.f("uq_criteria_rubric_version_id"),
        ),
    )
    op.create_table(
        "evidence",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("locator", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["candidate_id", "source_id"],
            ["sources.candidate_id", "sources.id"],
            name="fk_evidence_source",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_evidence_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("candidate_id", "id", name=op.f("pk_evidence")),
    )
    op.create_table(
        "matches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("rubric_version_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("passed_hard_filters", sa.Boolean(), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("scored_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["rubric_version_id"],
            ["rubric_versions.id"],
            name=op.f("fk_matches_rubric_version_id_rubric_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_matches")),
    )
    with op.batch_alter_table("matches", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_matches_job_id"), ["job_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_matches_profile_id"), ["profile_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_matches_rubric_version_id"),
            ["rubric_version_id"],
            unique=False,
        )

    op.create_table(
        "criterion_scores",
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("criterion_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_criterion_scores_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "match_id", "position", name=op.f("pk_criterion_scores")
        ),
    )


def downgrade() -> None:
    """Undo this migration."""
    op.drop_table("criterion_scores")
    with op.batch_alter_table("matches", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_matches_rubric_version_id"))
        batch_op.drop_index(batch_op.f("ix_matches_profile_id"))
        batch_op.drop_index(batch_op.f("ix_matches_job_id"))

    op.drop_table("matches")
    op.drop_table("evidence")
    op.drop_table("criteria")
    op.drop_table("sources")
    op.drop_table("rubric_versions")
    with op.batch_alter_table("job_history", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_job_history_job_id"))

    op.drop_table("job_history")
    with op.batch_alter_table("interview_questions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_interview_questions_candidate_id"))

    op.drop_table("interview_questions")
    op.drop_table("experiences")
    op.drop_table("claim_support")
    op.drop_table("candidate_skills")
    with op.batch_alter_table("candidate_history", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_candidate_history_candidate_id"))

    op.drop_table("candidate_history")
    op.drop_table("jobs")
    op.drop_table("candidates")
