"""add feeds.system_status

Revision ID: 6145c35f1ece
Revises: 5a54dacd62e3
Create Date: 2022-10-27 14:10:36.366706

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6145c35f1ece'
down_revision = '5a54dacd62e3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('feeds', sa.Column('system_status', sa.String()))


def downgrade():
    op.drop_column_column('feeds', 'system_status')
