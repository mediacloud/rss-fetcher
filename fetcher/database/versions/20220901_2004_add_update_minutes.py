"""add update_minutes

Revision ID: 24a9f51b9ceb
Revises: 184509e31258
Create Date: 2022-09-01 20:04:05.104722

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '24a9f51b9ceb'
down_revision = '184509e31258'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('feeds', sa.Column('update_minutes', sa.Integer()))


def downgrade():
    op.drop_column('feeds', 'update_minutes')
