"""add next_fetch_attempt

Revision ID: 184509e31258
Revises: ccbf360c92f8
Create Date: 2022-08-27 11:12:13.778494

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '184509e31258'
down_revision = 'ccbf360c92f8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('feeds', sa.Column('next_fetch_attempt', sa.DateTime())) # GMT please!


def downgrade():
    op.drop_column('feeds', 'next_fetch_attempt_deadline')
