"""add planned fields to applications

Revision ID: 8b80e9306e01
Revises: 82281bf711fc
Create Date: 2026-07-11 15:35:02.570155

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8b80e9306e01"
down_revision: Union[str, Sequence[str], None] = "82281bf711fc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate also flagged the vec0 virtual tables' own internal
    # shadow tables as "removed" (same real, recurring false positive
    # every prior migration touching this DB has hit) — stripped by
    # hand; only the new planned_fields column below is a genuine
    # change. server_default is required: the applications table already
    # exists (even though empty in the real dev DB right now), and
    # SQLite's ALTER TABLE ADD COLUMN rejects a NOT NULL column with no
    # default against an existing table.
    op.add_column(
        "applications",
        sa.Column("planned_fields", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("applications", "planned_fields")
