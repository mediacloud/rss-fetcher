"""update feed mc data

Revision ID: 324d49ce6374
Revises: 68cbc0802d68
Create Date: 2022-05-26 11:39:35.536749

Turns out when we first imported things there was a bug that made the media cloud feed and media ids not import,
which is a problem because now we want to actually use those! This script goes back to the raw data and adds in
the mc_feeds_id and mc_media_id values. It can take a few minutes to run, because it touches every row of the feeds
table.
"""
import logging
from alembic import op
from sqlalchemy.sql import text
import csv

# revision identifiers, used by Alembic.
revision = '324d49ce6374'
down_revision = '68cbc0802d68'
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade():
    pass


def downgrade():
    pass