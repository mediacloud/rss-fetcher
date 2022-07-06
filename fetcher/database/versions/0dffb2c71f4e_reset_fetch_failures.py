"""reset fetch failures

Revision ID: 0dffb2c71f4e
Revises: f7784f3c22e6
Create Date: 2022-07-06 10:52:59.762105

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0dffb2c71f4e'
down_revision = 'f7784f3c22e6'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE feeds SET last_fetch_failures=0")


def downgrade():
    pass
