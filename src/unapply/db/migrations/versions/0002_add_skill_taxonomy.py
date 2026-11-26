"""Add the skill taxonomy: canonical skills, their synonyms and relations.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.create_table(
        "taxonomy_skills",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_taxonomy_skills")),
    )
    op.create_table(
        "skill_relations",
        sa.Column("skill", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("related", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["related"],
            ["taxonomy_skills.name"],
            name=op.f("fk_skill_relations_related_taxonomy_skills"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill"],
            ["taxonomy_skills.name"],
            name=op.f("fk_skill_relations_skill_taxonomy_skills"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "skill", "kind", "related", name=op.f("pk_skill_relations")
        ),
    )
    with op.batch_alter_table("skill_relations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_skill_relations_related"), ["related"], unique=False
        )

    op.create_table(
        "skill_synonyms",
        sa.Column("synonym", sa.String(length=200), nullable=False),
        sa.Column("skill", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["skill"],
            ["taxonomy_skills.name"],
            name=op.f("fk_skill_synonyms_skill_taxonomy_skills"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("synonym", name=op.f("pk_skill_synonyms")),
    )
    with op.batch_alter_table("skill_synonyms", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_skill_synonyms_skill"), ["skill"], unique=False
        )


def downgrade() -> None:
    """Undo this migration."""
    with op.batch_alter_table("skill_synonyms", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_skill_synonyms_skill"))

    op.drop_table("skill_synonyms")
    with op.batch_alter_table("skill_relations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_skill_relations_related"))

    op.drop_table("skill_relations")
    op.drop_table("taxonomy_skills")
