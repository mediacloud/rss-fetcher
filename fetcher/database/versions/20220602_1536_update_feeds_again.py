"""update feeds again

Revision ID: f7784f3c22e6
Revises: 324d49ce6374
Create Date: 2022-06-02 15:22:35.542978

"""
from alembic import op
import csv
import logging
from typing import List

logger = logging.getLogger(__name__)


# revision identifiers, used by Alembic.
revision = 'f7784f3c22e6'
down_revision = '324d49ce6374'
branch_labels = None
depends_on = None


def upgrade():
    # grab the ids from the last import file
    pass


def downgrade():
    op.execute("DELETE from feeds WHERE import_round = 4")

