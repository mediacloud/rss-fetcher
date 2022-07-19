"""add story title index

Revision ID: 9bc05393d82c
Revises: 0a99c2299af2
Create Date: 2022-07-14 16:39:25.472880

"""
from alembic import op
# import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9bc05393d82c'
down_revision = '0a99c2299af2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('unique_story_title', 'stories', ['normalized_title_hash', 'media_id'])


def downgrade():
    op.drop_index('unique_story_title', 'stories')
