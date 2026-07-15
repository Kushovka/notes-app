"""notification deliveries

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-15

"""

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "note_id",
            sa.Integer(),
            sa.ForeignKey("notes.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_notification_deliveries_user_id", "notification_deliveries", ["user_id"])
    op.create_index("ix_notification_deliveries_note_id", "notification_deliveries", ["note_id"])


def downgrade():
    op.drop_index("ix_notification_deliveries_note_id", "notification_deliveries")
    op.drop_index("ix_notification_deliveries_user_id", "notification_deliveries")
    op.drop_table("notification_deliveries")
