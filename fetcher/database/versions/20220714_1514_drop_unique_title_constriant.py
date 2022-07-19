"""drop unique title constriant

Revision ID: 0a99c2299af2
Revises: aeea5e7ec71a
Create Date: 2022-07-14 15:11:47.844632

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0a99c2299af2'
down_revision = 'aeea5e7ec71a'
branch_labels = None
depends_on = None


def upgrade():
    # need to allow duplicate empty titles; will enforce at software level instead of DB level
    op.drop_index('unique_story_title', 'stories')


def downgrade():
    op.create_index('unique_story_title', 'stories', ['normalized_title_hash'], unique=True)
