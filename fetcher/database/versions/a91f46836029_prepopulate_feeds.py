"""prepopulate feeds

Revision ID: a91f46836029
Revises: bc56acb800bf
Create Date: 2022-02-17 12:05:34.020034

"""
from alembic import op
import sqlalchemy as sa

from fetcher import engine

# revision identifiers, used by Alembic.
revision = 'a91f46836029'
down_revision = 'bc56acb800bf'
branch_labels = None
depends_on = None


def upgrade():
    csv_file_path = 'data/feeds-2022-02-16.csv'
    with open(csv_file_path, 'r') as f:
        conn = engine.raw_connection()
        cursor = conn.cursor()
        cmd = 'COPY feeds(mc_feeds_id, mc_media_id, name, url, type, active) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)'
        cursor.copy_expert(cmd, f)
        conn.commit()
    pass


def downgrade():
    pass
