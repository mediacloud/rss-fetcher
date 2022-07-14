"""create fetch_events

Revision ID: aeea5e7ec71a
Revises: 0dffb2c71f4e
Create Date: 2022-07-14 14:44:02.347135

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func

# revision identifiers, used by Alembic.
revision = 'aeea5e7ec71a'
down_revision = '0dffb2c71f4e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'fetch_events',
        sa.Column('id', sa.BigInteger, primary_key=True),
        sa.Column('feed_id', sa.BigInteger),
        sa.Column('event', sa.String),
        sa.Column('note', sa.String),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=func.now()),
    )
    op.create_index('fetch_events_feeds_id', 'fetch_events', ['feed_id'])
    op.create_index('fetch_events_created_at', 'fetch_events', ['created_at'])


def downgrade():
    op.drop_table('fetch_events')
    op.drop_index('fetch_events_feeds_id', 'fetch_events')
    #pass