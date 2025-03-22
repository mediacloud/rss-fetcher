"""update-feeds

Revision ID: a83638d0280b
Revises: 8f9a42e8903c
Create Date: 2022-05-16 15:43:26.041869

"""

# revision identifiers, used by Alembic.
revision = 'a83638d0280b'
down_revision = '8f9a42e8903c'
branch_labels = None
depends_on = None


# Data generated with this command on the production database:
#   psql -c "\copy (select * from feeds f where f.active=true and f.type='syndicated' and f.last_new_story_time > now() - '180 days'::interval) TO ‘/tmp/feeds-2022-05-16.csv' CSV HEADER;"
def upgrade():
    pass


def downgrade():
    pass
