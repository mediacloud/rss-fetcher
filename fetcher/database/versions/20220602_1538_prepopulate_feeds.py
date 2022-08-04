"""prepopulate feeds

Revision ID: a91f46836029
Revises: bc56acb800bf
Create Date: 2022-02-17 12:05:34.020034

"""
from alembic import op
import csv

# revision identifiers, used by Alembic.
revision = 'a91f46836029'
down_revision = 'bc56acb800bf'
branch_labels = None
depends_on = None


# Data generated with this command on the production database:
#   psql -c "\copy (select * from feeds f where f.active=true and f.type='syndicated' and f.last_new_story_time > now() - '180 days'::interval) TO ‘/tmp/feeds-2022-02-16.csv' CSV HEADER;"
def upgrade():
    pass


def downgrade():
    op.execute("delete from feeds")
