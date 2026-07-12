"""add name email linkedin location to applicant profile

Revision ID: 59409f1af06f
Revises: 9194e5155074
Create Date: 2026-07-12 19:50:43.879297

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "59409f1af06f"
down_revision: Union[str, Sequence[str], None] = "9194e5155074"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate also flagged the vec0/FTS5 virtual tables' own internal
    # shadow tables as "removed" (same real, recurring false positive every
    # prior migration touching this DB has hit) — stripped by hand; only
    # the four new applicant_profile columns below are a genuine change.
    op.add_column("applicant_profile", sa.Column("full_name", sa.String(), nullable=True))
    op.add_column("applicant_profile", sa.Column("email", sa.String(), nullable=True))
    op.add_column("applicant_profile", sa.Column("linkedin_url", sa.String(), nullable=True))
    op.add_column("applicant_profile", sa.Column("location", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("applicant_profile", "location")
    op.drop_column("applicant_profile", "linkedin_url")
    op.drop_column("applicant_profile", "email")
    op.drop_column("applicant_profile", "full_name")
