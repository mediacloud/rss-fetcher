"""add poll_minutes

Revision ID: 5332cd0c7e48
Revises: dfb30173c4cc
Create Date: 2023-01-11 12:37:11.136323

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5332cd0c7e48'
down_revision = 'dfb30173c4cc'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('feeds', sa.Column('poll_minutes', sa.Integer()))


def downgrade():
    op.drop_column('feeds', 'poll_minutes')
