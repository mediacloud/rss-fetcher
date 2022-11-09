"""convert last_fetch_failures to float

Revision ID: e549e03d2f7a
Revises: 6145c35f1ece
Create Date: 2022-11-06 12:06:44.185428

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e549e03d2f7a'
down_revision = '6145c35f1ece'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('feeds', 'last_fetch_failures', type_=sa.REAL)


def downgrade():
    op.alter_column('feeds', 'last_fetch_failures', type_=sa.Integer)


