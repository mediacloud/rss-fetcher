"""update-feeds

Revision ID: a83638d0280b
Revises: 8f9a42e8903c
Create Date: 2022-05-16 15:43:26.041869

"""
import csv
from alembic import op
import sqlalchemy as sa

from fetcher.database.versions.a91f46836029_prepopulate_feeds import feeds_table

# revision identifiers, used by Alembic.
revision = 'a83638d0280b'
down_revision = '8f9a42e8903c'
branch_labels = None
depends_on = None


# Data generated with this command on the production database:
#   psql -c "\copy (select * from feeds f where f.active=true and f.type='syndicated' and f.last_new_story_time > now() - '180 days'::interval) TO ‘/tmp/feeds-2022-05-16.csv' CSV HEADER;"
def upgrade():
    # 133,830 -> 144,269
    # add a column to track import batches
    op.add_column('feeds', sa.Column('import_round', sa.Integer()))
    op.execute("UPDATE feeds SET import_round = 1")
    # grab the ids from the last import file
    first_csv_file_path = 'data/feeds-2022-02-16.csv'
    with open(first_csv_file_path) as csvfile:
        reader = csv.DictReader(csvfile)
        prepopulated_ids = [r['feeds_id'] for r in reader]
    # insert (https://alembic.sqlalchemy.org/en/latest/ops.html?highlight=bulk_insert#alembic.operations.Operations.bulk_insert)
    # now load in new file, and import all except already existing ides
    new_csv_file_path = 'data/feeds-2022-05-16.csv'
    with open(new_csv_file_path) as csvfile:
        reader = csv.DictReader(csvfile)
        data = [r for r in reader]
        new_data = [d for d in data if d['feeds_id'] not in prepopulated_ids]
        for r in new_data:
            r['active'] = True if r['active'] == 't' else False
            r['import_round'] = 2
        op.bulk_insert(feeds_table, new_data)


def downgrade():
    op.execute("DELETE from feeds WHERE import_round = 2")
