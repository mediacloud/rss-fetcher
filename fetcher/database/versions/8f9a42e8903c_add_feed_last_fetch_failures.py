"""add feed last_fetch_failures

Revision ID: 8f9a42e8903c
Revises: 35fe32618767
Create Date: 2022-04-27 12:35:51.027664

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8f9a42e8903c'
down_revision = '35fe32618767'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('feeds', sa.Column('last_fetch_failures', sa.Integer()))


def downgrade():
    op.drop_column('feeds', 'last_fetch_failures')
