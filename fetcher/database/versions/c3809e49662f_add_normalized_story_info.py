"""add story normalized_url

Revision ID: c3809e49662f
Revises: a83638d0280b
Create Date: 2022-05-25 15:21:31.802512

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3809e49662f'
down_revision = 'a83638d0280b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('stories', sa.Column('normalized_url', sa.Integer()))
    op.add_column('stories', sa.Column('normalized_title', sa.Integer()))
    op.add_column('stories', sa.Column('normalized_title_hash', sa.Integer()))
    op.drop_constraint('stories_unique_url', 'stories')  # we want normalized to be unique now
    op.create_index('unique_story_url', 'stories', ['normalized_url'], unique=True)
    op.create_index('unique_story_title', 'stories', ['normalized_title_hash'], unique=True)


def downgrade():
    op.drop_column('stories', 'normalized_url')
    op.drop_column('stories', 'normalized_title')
    op.add_column('stories', sa.Column('normalized_title_hash', sa.Integer()))
    op.drop_index('unique_story_url')
    op.drop_index('unique_story_title')
