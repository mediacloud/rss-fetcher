"""drop duplicate feeds ids

Revision ID: 313f51e4eefd
Revises: 9bc05393d82c
Create Date: 2022-08-03 20:39:22.905810

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '313f51e4eefd'
down_revision = '9bc05393d82c'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('feeds', 'mc_feeds_id')
    #op.drop_column('feeds', 'import_round')
    op.alter_column('feeds', 'mc_media_id', new_column_name='media_id')
    op.add_column('feeds', sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()')))


def downgrade():
    op.add_column('feeds', sa.Column('mc_feeds_id', sa.BigInteger))
    #op.add_column('feeds', sa.Column('import_round', sa.Integer))
    op.alter_column('feeds', 'media_id', new_column_name='mc_media_id')
    op.drop_column('feeds', 'created_at')
