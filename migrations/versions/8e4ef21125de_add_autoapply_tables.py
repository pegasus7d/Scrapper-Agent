"""add autoapply tables

Revision ID: 8e4ef21125de
Revises: bddcd96eaee8
Create Date: 2026-07-11 00:48:50.196860

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8e4ef21125de"
down_revision: Union[str, Sequence[str], None] = "bddcd96eaee8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate also flagged every vec0/FTS5 virtual table's own
    # internal shadow tables as "removed" (same real, recurring false
    # positive every prior migration touching this DB has hit) — stripped
    # by hand; only the three new tables and the one new column below are
    # a genuine change. server_default is required on auto_apply_blocked,
    # not optional: the real dev database already has 2979 real company
    # rows, and SQLite's ALTER TABLE ADD COLUMN rejects a NOT NULL column
    # with no default against a non-empty table.
    #
    # _table_exists guards below: an earlier, interrupted upgrade attempt
    # (before this migration had its server_default fix) already created
    # these three tables against the real dev DB and then failed on
    # add_column, leaving them empty but present with alembic_version not
    # advanced. Verified empty and schema-identical before relying on this
    # guard — skip re-creating them rather than dropping and recreating.
    if not _table_exists("autoapply_settings"):
        op.create_table(
            "autoapply_settings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("kill_switch_enabled", sa.Boolean(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _table_exists("applications"):
        op.create_table(
            "applications",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("job_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("risk_level", sa.String(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("error", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _table_exists("application_events"):
        op.create_table(
            "application_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("application_id", sa.Integer(), nullable=False),
            sa.Column("parent_event_id", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(), nullable=False),
            sa.Column("success", sa.Boolean(), nullable=False),
            sa.Column("detail", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
            sa.ForeignKeyConstraint(["parent_event_id"], ["application_events.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    op.add_column(
        "companies",
        sa.Column("auto_apply_blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("companies", "auto_apply_blocked")
    op.drop_table("application_events")
    op.drop_table("applications")
    op.drop_table("autoapply_settings")
