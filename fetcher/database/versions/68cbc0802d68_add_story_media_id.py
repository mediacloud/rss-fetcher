"""add story media_id

Revision ID: 68cbc0802d68
Revises: c3809e49662f
Create Date: 2022-05-25 15:37:35.766908

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '68cbc0802d68'
down_revision = 'c3809e49662f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('stories', sa.Column('media_id', sa.BigInteger()))


def downgrade():
    op.drop_column('stories', 'media_id')
