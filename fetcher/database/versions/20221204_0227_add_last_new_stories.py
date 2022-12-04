"""add last_new_stories

Revision ID: 91fae5a8a02e
Revises: e549e03d2f7a
Create Date: 2022-12-04 02:27:23.386149

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '91fae5a8a02e'
down_revision = 'e549e03d2f7a'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('feeds', sa.Column('last_new_stories', sa.DateTime())) # GMT


def downgrade():
    op.add_column('feeds', 'last_new_stories')
