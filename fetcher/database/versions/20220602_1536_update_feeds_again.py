"""update feeds again

Revision ID: f7784f3c22e6
Revises: 324d49ce6374
Create Date: 2022-06-02 15:22:35.542978

"""
from alembic import op
import csv
import logging
from typing import List

from fetcher.database.helpers import feeds_table

logger = logging.getLogger(__name__)


# revision identifiers, used by Alembic.
revision = 'f7784f3c22e6'
down_revision = '324d49ce6374'
branch_labels = None
depends_on = None


# psql --csv -c "select * from feeds where active = 't' and type = 'syndicated' and last_successful_download_time >= '2022-05-01' " > feeds-2022-06-02.csv

def _feed_ids_from_file(filepath: str) -> List[int]:
    with open(filepath) as csvfile:
        reader = csv.DictReader(csvfile)
        existing_ids = [r['feeds_id'] for r in reader]
    return existing_ids


def upgrade():
    # grab the ids from the last import file
    existing_ids = set(_feed_ids_from_file('data/feeds-2022-02-16.csv') +
                       _feed_ids_from_file('data/feeds-2022-05-16.csv'))
    logger.error("Found {} existing feed ids".format(len(existing_ids)))
    # insert (https://alembic.sqlalchemy.org/en/latest/ops.html?highlight=bulk_insert#alembic.operations.Operations.bulk_insert)
    # now load in new file, and import all except already existing ides
    new_csv_file_path = 'data/feeds-2022-06-02.csv'
    with open(new_csv_file_path) as csvfile:
        reader = csv.DictReader(csvfile)
        data = [r for r in reader]
        new_data = [d for d in data if d['feeds_id'] not in existing_ids]
        for row in new_data:
            row['active'] = True if row['active'] == 't' else False
            row['mc_media_id'] = int(row['media_id'])
            row['mc_feeds_id'] = int(row['feeds_id'])
            row['import_round'] = 4
        logger.error("Ready to import {} new feeds".format(len(new_data)))
        op.bulk_insert(feeds_table, new_data)


def downgrade():
    op.execute("DELETE from feeds WHERE import_round = 4")

