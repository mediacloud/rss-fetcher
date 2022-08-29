"""add next_fetch_attempt, queued, system_enabled; defaults for active, last_fetch_failures

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
    op.execute("UPDATE feeds SET active = true WHERE active IS NULL")
    op.alter_column('feeds', 'active', nullable=False, server_default=sa.text('true'))
    op.execute("UPDATE feeds SET last_fetch_failures = 0 WHERE last_fetch_failures IS NULL")
    op.alter_column('feeds', 'last_fetch_failures', nullable=False, server_default=sa.text('0'))
    op.add_column('feeds', sa.Column('next_fetch_attempt', sa.DateTime())) # GMT
    op.add_column('feeds', sa.Column('queued', sa.Boolean,
                                     nullable=False, server_default=sa.text('false')))
    op.add_column('feeds', sa.Column('system_enabled', sa.Boolean,
                                     nullable=False, server_default=sa.text('true')))

def downgrade():
    op.alter_column('feeds', 'active', nullable=True, server_default=False)
    op.alter_column('feeds', 'last_fetch_failures', nullable=True, server_default=False)
    op.drop_column('feeds', 'next_fetch_attempt')
    op.drop_column('feeds', 'queued')
    op.drop_column('feeds', 'system_enabled')
