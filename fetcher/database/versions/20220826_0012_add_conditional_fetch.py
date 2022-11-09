"""add conditional fetch

Revision ID: ccbf360c92f8
Revises: 056d7ddcf6b5
Create Date: 2022-08-26 00:12:58.388887

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ccbf360c92f8'
down_revision = '056d7ddcf6b5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('feeds', sa.Column('http_etag', sa.String))
    op.add_column('feeds', sa.Column('http_last_modified', sa.String))


def downgrade():
    op.drop_column('feeds', 'http_etag')
    op.drop_column('feeds', 'http_last_modified')
