"""add applicant profile table

Revision ID: 1ba87578c3b3
Revises: 8e4ef21125de
Create Date: 2026-07-11 01:52:06.856970

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1ba87578c3b3"
down_revision: Union[str, Sequence[str], None] = "8e4ef21125de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate also flagged the vec0 virtual tables' own internal
    # shadow tables as "removed" (same real, recurring false positive
    # every prior migration touching this DB has hit) — stripped by hand;
    # only the new applicant_profile table below is a genuine change.
    op.create_table(
        "applicant_profile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("current_salary", sa.String(), nullable=True),
        sa.Column("expected_salary", sa.String(), nullable=True),
        sa.Column("work_authorization", sa.String(), nullable=True),
        sa.Column("relocation", sa.Boolean(), nullable=True),
        sa.Column("start_date_availability", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("applicant_profile")
