"""indices: add feeds_system_enabled, feeds_next_fetch_attempt, drop feeds_last_fetch_attempt

Revision ID: 5a54dacd62e3
Revises: 9d6e6264b580
Create Date: 2022-10-27 14:06:27.295729

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '5a54dacd62e3'
down_revision = '9d6e6264b580'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index('feeds_last_fetch_attempt', 'feeds')
    op.create_index('feeds_system_enabled', 'feeds', ['system_enabled'])
    op.create_index('feeds_next_fetch_attempt', 'feeds', ['last_fetch_attempt'])


def downgrade():
    op.create_index('feeds_last_fetch_attempt', 'feeds', ['last_fetch_attempt'])
