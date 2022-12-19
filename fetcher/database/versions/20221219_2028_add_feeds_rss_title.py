"""add feeds.rss_title

Revision ID: dfb30173c4cc
Revises: b22da3d31ffb
Create Date: 2022-12-19 20:28:44.959123

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dfb30173c4cc'
down_revision = 'b22da3d31ffb'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('feeds', sa.Column('rss_title', sa.String()))


def downgrade():
    op.drop_column_column('feeds', 'rss_title')
