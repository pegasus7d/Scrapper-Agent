"""add job status tracking

Revision ID: 25228abafa00
Revises: 5665565b8cbe
Create Date: 2026-07-10 14:35:15.682313

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "25228abafa00"
down_revision: Union[str, Sequence[str], None] = "5665565b8cbe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate also flagged the vec0/FTS5 virtual tables' own internal
    # shadow tables as "removed" (same false-positive as the previous two
    # migrations) — stripped by hand; only the two new columns below are a
    # genuine change. server_default is required here, not optional: the
    # real dev database already has real job rows, and SQLite's ALTER
    # TABLE ADD COLUMN rejects a NOT NULL column with no default against a
    # non-empty table.
    op.add_column(
        "jobs",
        sa.Column("status", sa.String(), nullable=False, server_default="none"),
    )
    op.add_column("jobs", sa.Column("status_changed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("jobs", "status_changed_at")
    op.drop_column("jobs", "status")
