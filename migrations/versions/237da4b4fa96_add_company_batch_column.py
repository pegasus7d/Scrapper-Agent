"""add company batch column

Revision ID: 237da4b4fa96
Revises: 25228abafa00
Create Date: 2026-07-10 18:02:34.659948

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "237da4b4fa96"
down_revision: Union[str, Sequence[str], None] = "25228abafa00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate also flagged the vec0/FTS5 virtual tables' own internal
    # shadow tables as "removed" (same false-positive as every prior
    # migration) — stripped by hand; only the real column below is a
    # genuine change.
    op.add_column("companies", sa.Column("batch", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("companies", "batch")
