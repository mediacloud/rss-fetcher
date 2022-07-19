"""make story url unique

Revision ID: 35fe32618767
Revises: 95a50840dc89
Create Date: 2022-02-18 09:04:27.127883

"""
from alembic import op
# import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '35fe32618767'
down_revision = '95a50840dc89'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint('stories_unique_url', 'stories', ['url'])


def downgrade():
    op.drop_constraint('stories_unique_url', 'stories')
