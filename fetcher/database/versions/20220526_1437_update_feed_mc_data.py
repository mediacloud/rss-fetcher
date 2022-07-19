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

from fetcher.database.helpers import feeds_table

# revision identifiers, used by Alembic.
revision = '324d49ce6374'
down_revision = '68cbc0802d68'
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade():
    # make queries by feed url faster
    op.create_index('feed_url', 'feeds', ['url'])
    # now add in the columns
    conn = op.get_bind()
    csv_file_paths = ['data/feeds-2022-02-16.csv', 'data/feeds-2022-05-16.csv']
    dupe_index = {}
    for f in csv_file_paths:
        new_data = []
        with open(f) as csvfile:
            reader = csv.DictReader(csvfile)
            data = [row for row in reader]
            for row in data:
                current_url = row['url']
                if current_url in dupe_index:
                    current_dupe_index = dupe_index[current_url] + 1
                else:
                    current_dupe_index = 0
                dupe_index[current_url] = current_dupe_index
                select_sql = text("SELECT id FROM FEEDS WHERE url = :url ORDER BY id ASC")
                res = conn.execute(select_sql, url=current_url)
                results = res.fetchall()
                if current_dupe_index < len(results):  # extra safety
                    if len(results) > 0:
                        local_feed_id = results[current_dupe_index][0]
                        update_sql = text("UPDATE feeds SET mc_feeds_id=:mc_feeds_id, mc_media_id=:mc_media_id WHERE id=:id")
                        conn.execute(update_sql, mc_feeds_id=row['feeds_id'], mc_media_id=row['media_id'], id=local_feed_id)
                    else:
                        row['active'] = True if row['active'] == 't' else False
                        row['mc_media_id'] = row['media_id']
                        row['mc_feeds_id'] = row['feeds_id']
                        row['import_round'] = 3
                        new_data.append(row)
        # now save any feeds that were missing for some reason
        if len(new_data) > 0:
            op.bulk_insert(feeds_table, new_data)
    # and drop the index because we don't usually lookup feeds by url
    op.drop_index('feed_url', 'feeds')


def downgrade():
    conn = op.get_bind()
    conn.execute("UPDATE feeds SET mc_feeds_id=NULL, mc_media_id=NULL")
