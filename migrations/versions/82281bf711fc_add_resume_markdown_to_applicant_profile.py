"""add resume markdown to applicant profile

Revision ID: 82281bf711fc
Revises: 1ba87578c3b3
Create Date: 2026-07-11 14:58:53.788343

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "82281bf711fc"
down_revision: Union[str, Sequence[str], None] = "1ba87578c3b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate also flagged the vec0 virtual tables' own internal
    # shadow tables as "removed" (same real, recurring false positive
    # every prior migration touching this DB has hit) — stripped by hand;
    # only the new resume_markdown column below is a genuine change.
    op.add_column("applicant_profile", sa.Column("resume_markdown", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("applicant_profile", "resume_markdown")
