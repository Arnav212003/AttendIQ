"""add one-time voice liveness challenge nonce

Revision ID: e31a9f4c7d20
Revises: cf47691b6bae
"""
from alembic import op
import sqlalchemy as sa

revision = "e31a9f4c7d20"
down_revision = "cf47691b6bae"
branch_labels = None
depends_on = None


def upgrade():
    # Nullable keeps this migration safe for existing replay-log rows. New
    # active-liveness attempts populate the nonce; old exact-hash records stay
    # valid without requiring a backfill.
    with op.batch_alter_table("voice_recognition_logs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("challenge_nonce", sa.String(length=32), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_voice_recognition_logs_challenge_nonce"),
            ["challenge_nonce"],
            unique=True,
        )


def downgrade():
    with op.batch_alter_table("voice_recognition_logs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_voice_recognition_logs_challenge_nonce"))
        batch_op.drop_column("challenge_nonce")
