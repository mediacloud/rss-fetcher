"""add stories table

Revision ID: 95a50840dc89
Revises: a91f46836029
Create Date: 2022-02-17 12:37:44.960582

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '95a50840dc89'
down_revision = 'a91f46836029'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'stories',
        sa.Column('id', sa.BigInteger, primary_key=True),
        sa.Column('feed_id', sa.BigInteger),
        sa.Column('url', sa.String),
        sa.Column('guid', sa.String),
        sa.Column('published_at', sa.DateTime(timezone=True)),
        sa.Column('fetched_at', sa.DateTime(timezone=True)),
        sa.Column('domain', sa.String),
    )
    op.create_index('stories_feed_id', 'stories', ['feed_id'])
    op.create_index('stories_domain', 'stories', ['domain'])
    op.create_index('stories_published_at', 'stories', ['published_at'])
    op.create_index('stories_fetched_at', 'stories', ['fetched_at'])


def downgrade():
    op.drop_table('stories')
