"""rename media_id to sources_id

Revision ID: 056d7ddcf6b5
Revises: 313f51e4eefd
Create Date: 2022-08-17 15:54:10.511960

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '056d7ddcf6b5'
down_revision = '313f51e4eefd'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index('feeds_mc_media_id', 'feeds')
    op.alter_column('feeds', 'media_id', new_column_name='sources_id')
    op.create_index('feeds_sources_id', 'feeds', ['sources_id'])
    op.alter_column('stories', 'media_id', new_column_name='sources_id')
    op.drop_column('feeds', 'type')


def downgrade():
    op.drop_index('feeds_sources_id', 'feeds')
    op.alter_column('feeds', 'sources_id', new_column_name='media_id')
    op.create_index('feeds_mc_media_id', 'feeds', ['media_id'])
    op.alter_column('stories', 'sources_id', new_column_name='media_id')
    op.add_column('stories', sa.Column('type', sa.String))
