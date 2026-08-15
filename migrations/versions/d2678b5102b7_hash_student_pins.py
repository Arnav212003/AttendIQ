"""hash student pins

Revision ID: d2678b5102b7
Revises: bc6572c6f0d8
Create Date: 2026-08-14 17:43:07.978638

"""
from alembic import op
import sqlalchemy as sa
from werkzeug.security import generate_password_hash


# revision identifiers, used by Alembic.
revision = 'd2678b5102b7'
down_revision = 'bc6572c6f0d8'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: add pin_hash as nullable first - a NOT NULL column with no
    # default would fail immediately on a table that already has rows.
    with op.batch_alter_table('students', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pin_hash', sa.String(length=255), nullable=True))

    # Step 2: backfill pin_hash from each existing row's plaintext pin_code,
    # so students registered before this migration keep working with their
    # existing PIN rather than being silently locked out.
    connection = op.get_bind()
    students_table = sa.table(
        'students',
        sa.column('id', sa.Integer),
        sa.column('pin_code', sa.String),
        sa.column('pin_hash', sa.String),
    )
    existing_rows = connection.execute(
        sa.select(students_table.c.id, students_table.c.pin_code)
    ).fetchall()

    for student_id, plain_pin in existing_rows:
        connection.execute(
            students_table.update()
            .where(students_table.c.id == student_id)
            .values(pin_hash=generate_password_hash(plain_pin or "0000"))
        )

    # Step 3: now every row has a hash - enforce NOT NULL and drop the old
    # plaintext column.
    with op.batch_alter_table('students', schema=None) as batch_op:
        batch_op.alter_column('pin_hash', existing_type=sa.String(length=255), nullable=False)
        batch_op.drop_column('pin_code')


def downgrade():
    # Note: downgrade cannot recover the original plaintext PINs (they were
    # already hashed and pin_code was dropped) - it recreates the column with
    # placeholder values, which will require students to be re-issued PINs.
    with op.batch_alter_table('students', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pin_code', sa.VARCHAR(length=4), nullable=True))
        batch_op.drop_column('pin_hash')
