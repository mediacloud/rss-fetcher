"""add stories_sources_id

Revision ID: 73d7a4ca0e7b
Revises: 5332cd0c7e48
Create Date: 2024-08-15 23:13:18.484530

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '73d7a4ca0e7b'
down_revision = '5332cd0c7e48'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('stories_sources_id', 'stories', ['sources_id'])


def downgrade():
    op.drop_index('stories_sources_id', 'stories')
