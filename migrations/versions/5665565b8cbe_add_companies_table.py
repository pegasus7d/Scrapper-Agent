"""add companies table

Revision ID: 5665565b8cbe
Revises: 94f76054fb54
Create Date: 2026-07-10 12:27:23.677087

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5665565b8cbe"
down_revision: Union[str, Sequence[str], None] = "94f76054fb54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate also flagged the vec0/FTS5 virtual tables' own internal
    # shadow tables as "removed" (same false-positive as the initial
    # migration, 94f76054fb54) — stripped by hand; only the real new table
    # below is a genuine change.
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=True),
        sa.Column("ats_provider", sa.String(), nullable=True),
        sa.Column("discovered_at", sa.DateTime(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("companies")
