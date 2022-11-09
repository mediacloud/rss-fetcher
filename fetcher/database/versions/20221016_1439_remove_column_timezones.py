"""remove column timezones

Revision ID: ffc26b3bb9fc
Revises: 24a9f51b9ceb
Create Date: 2022-10-16 14:39:23.566599

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'ffc26b3bb9fc'
down_revision = '24a9f51b9ceb'
branch_labels = None
depends_on = None


def _flip(tz):
    op.alter_column('feeds', 'last_fetch_attempt', type_=sa.DateTime(timezone=tz))
    op.alter_column('feeds', 'last_fetch_success', type_=sa.DateTime(timezone=tz))
    op.alter_column('fetch_events', 'created_at', type_=sa.DateTime(timezone=tz))
    op.alter_column('stories', 'published_at', type_=sa.DateTime(timezone=tz))
    op.alter_column('stories', 'fetched_at', type_=sa.DateTime(timezone=tz))


def upgrade():
    _flip(False)


def downgrade():
    _flip(True)
