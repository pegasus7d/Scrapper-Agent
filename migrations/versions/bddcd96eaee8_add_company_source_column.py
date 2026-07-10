"""add company source column

Revision ID: bddcd96eaee8
Revises: 237da4b4fa96
Create Date: 2026-07-10 18:15:11.453498

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bddcd96eaee8"
down_revision: Union[str, Sequence[str], None] = "237da4b4fa96"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate also flagged the vec0/FTS5 virtual tables' own internal
    # shadow tables as "removed" (same false-positive as every prior
    # migration) — stripped by hand; only the real column below is a
    # genuine change. server_default='yc' is required, not optional: the
    # real dev database already has 120 real company rows, all of them
    # genuinely YC-discovered (this column didn't exist before this step),
    # and SQLite's ALTER TABLE ADD COLUMN rejects a NOT NULL column with
    # no default against a non-empty table.
    op.add_column(
        "companies",
        sa.Column("source", sa.String(), nullable=False, server_default="yc"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("companies", "source")
