"""add pin_code to students

Revision ID: fd26d9d1b9fb
Revises: bce884492088
Create Date: 2026-08-14 17:22:24.437671

"""
import random

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fd26d9d1b9fb'
down_revision = 'bce884492088'
branch_labels = None
depends_on = None


def _generate_pin():
    return f"{random.randint(0, 9999):04d}"


def upgrade():
    # Step 1: add the column as nullable - required so this doesn't fail on
    # a table that already has rows (a NOT NULL column with no default would
    # error immediately on any existing student).
    with op.batch_alter_table('students', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pin_code', sa.String(length=4), nullable=True))

    # Step 2: backfill existing rows with a randomly generated PIN. Any
    # student registered before this migration will need their PIN re-shared
    # by their teacher (there is no way to recover/notify automatically here).
    connection = op.get_bind()
    students_table = sa.table('students', sa.column('id', sa.Integer), sa.column('pin_code', sa.String))
    existing_ids = [row[0] for row in connection.execute(sa.select(students_table.c.id))]

    for student_id in existing_ids:
        connection.execute(
            students_table.update()
            .where(students_table.c.id == student_id)
            .values(pin_code=_generate_pin())
        )

    # Step 3: now that every row has a value, enforce NOT NULL.
    with op.batch_alter_table('students', schema=None) as batch_op:
        batch_op.alter_column('pin_code', existing_type=sa.String(length=4), nullable=False)


def downgrade():
    with op.batch_alter_table('students', schema=None) as batch_op:
        batch_op.drop_column('pin_code')
