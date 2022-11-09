"""add feeds.http_304

Revision ID: 9d6e6264b580
Revises: ffc26b3bb9fc
Create Date: 2022-10-24 12:34:07.998799

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9d6e6264b580'
down_revision = 'ffc26b3bb9fc'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('feeds', sa.Column('http_304', sa.Boolean()))


def downgrade():
    op.drop_column('feeds', 'http_304')
