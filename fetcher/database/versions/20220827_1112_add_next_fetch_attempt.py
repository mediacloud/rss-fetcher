"""add next_fetch_attempt, queued, system_enabled

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
    op.add_column('feeds', sa.Column('next_fetch_attempt', sa.DateTime())) # GMT
    op.add_column('feeds', sa.Column('queued', sa.Boolean,
                                     nullable=False, server_default=sa.text('false')))
    op.add_column('feeds', sa.Column('system_enabled', sa.Boolean,
                                     nullable=False, server_default=sa.text('true')))


def downgrade():
    op.drop_column('feeds', 'next_fetch_attempt')
    op.drop_column('feeds', 'queued')
    op.drop_column('feeds', 'system_enabled')
