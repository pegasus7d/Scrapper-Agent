"""add field detection cache table

Revision ID: 9194e5155074
Revises: 8b80e9306e01
Create Date: 2026-07-12 01:36:19.529447

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9194e5155074"
down_revision: Union[str, Sequence[str], None] = "8b80e9306e01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate also flagged the vec0 virtual tables' own internal
    # shadow tables as "removed" (same real, recurring false positive
    # every prior migration touching this DB has hit) — stripped by
    # hand; only the new field_detection_cache table below is a genuine
    # change.
    op.create_table(
        "field_detection_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ats_provider", sa.String(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("field_map", sa.JSON(), nullable=False),
        sa.Column("cached_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("field_detection_cache")
