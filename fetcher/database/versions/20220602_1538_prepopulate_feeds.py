"""prepopulate feeds

Revision ID: a91f46836029
Revises: bc56acb800bf
Create Date: 2022-02-17 12:05:34.020034

"""
from alembic import op
import csv

from fetcher.database.helpers import feeds_table

# revision identifiers, used by Alembic.
revision = 'a91f46836029'
down_revision = 'bc56acb800bf'
branch_labels = None
depends_on = None


# Data generated with this command on the production database:
#   psql -c "\copy (select * from feeds f where f.active=true and f.type='syndicated' and f.last_new_story_time > now() - '180 days'::interval) TO ‘/tmp/feeds-2022-02-16.csv' CSV HEADER;"
def upgrade():
    csv_file_path = 'data/feeds-2022-02-16.csv'
    # insert (https://alembic.sqlalchemy.org/en/latest/ops.html?highlight=bulk_insert#alembic.operations.Operations.bulk_insert)
    with open(csv_file_path) as csvfile:
        reader = csv.DictReader(csvfile)
        data = [r for r in reader]
        for r in data:
            r['active'] = True if r['active'] == 't' else False
        op.bulk_insert(feeds_table, data)


def downgrade():
    op.execute("delete from feeds")
