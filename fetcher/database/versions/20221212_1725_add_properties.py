"""add properties

Revision ID: b22da3d31ffb
Revises: 91fae5a8a02e
Create Date: 2022-12-12 17:25:59.320833

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b22da3d31ffb'
down_revision = '91fae5a8a02e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'properties',
        sa.Column('section', sa.String, primary_key=True, nullable=False),
        sa.Column('key', sa.String, primary_key=True, nullable=False),
        sa.Column('value', sa.String),
    )


def downgrade():
    op.drop_table('properties')
