"""create feeds table

Revision ID: bc56acb800bf
Revises: 
Create Date: 2022-02-17 12:00:53.437355

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bc56acb800bf'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'feeds',
        sa.Column('id', sa.BigInteger, primary_key=True),
        sa.Column('mc_feeds_id', sa.BigInteger),
        sa.Column('mc_media_id', sa.BigInteger),
        sa.Column('name', sa.String),
        sa.Column('url', sa.String),
        sa.Column('type', sa.String),
        sa.Column('active', sa.Boolean),
        sa.Column('last_fetch_attempt', sa.DateTime(timezone=True)),
        sa.Column('last_fetch_success', sa.DateTime(timezone=True)),
        sa.Column('last_fetch_hash', sa.String),
    )
    op.create_index('feeds_last_fetch_attempt', 'feeds', ['last_fetch_attempt'])
    op.create_index('feeds_mc_feeds_id', 'feeds', ['mc_feeds_id'])
    op.create_index('feeds_mc_media_id', 'feeds', ['mc_media_id'])
    op.create_index('feeds_type', 'feeds', ['type'])
    op.create_index('feeds_active', 'feeds', ['active'])


def downgrade():
    op.drop_table('feeds')
