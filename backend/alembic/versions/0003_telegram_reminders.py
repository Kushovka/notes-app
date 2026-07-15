"""telegram reminders

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-15

"""

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("telegram_chat_id", sa.String(64), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "telegram_notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("users", sa.Column("telegram_link_token", sa.String(64), nullable=True))
    op.add_column(
        "users", sa.Column("telegram_linked_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
    )
    op.create_index("ix_users_telegram_chat_id", "users", ["telegram_chat_id"])
    op.create_unique_constraint("uq_users_telegram_link_token", "users", ["telegram_link_token"])

    op.add_column(
        "notes",
        sa.Column("telegram_reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notes",
        sa.Column(
            "telegram_reminder_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column("notes", sa.Column("telegram_reminder_last_error", sa.Text(), nullable=True))
    op.create_index(
        "ix_notes_telegram_reminder_sent_at",
        "notes",
        ["telegram_reminder_sent_at"],
    )


def downgrade():
    op.drop_index("ix_notes_telegram_reminder_sent_at", "notes")
    op.drop_column("notes", "telegram_reminder_last_error")
    op.drop_column("notes", "telegram_reminder_attempts")
    op.drop_column("notes", "telegram_reminder_sent_at")

    op.drop_constraint("uq_users_telegram_link_token", "users", type_="unique")
    op.drop_index("ix_users_telegram_chat_id", "users")
    op.drop_column("users", "timezone")
    op.drop_column("users", "telegram_linked_at")
    op.drop_column("users", "telegram_link_token")
    op.drop_column("users", "telegram_notifications_enabled")
    op.drop_column("users", "telegram_chat_id")
