import logging
import datetime as dt
from sqlalchemy import text
import sys
from subprocess import call
import os
import csv

from fetcher.database import engine, Session
import fetcher.database.models as models
from fetcher.logargparse import LogArgumentParser


def _run_psql_command(cmd: str):
    db_uri = os.getenv('DATABASE_URI')
    call(['psql', '-Atx', db_uri, '-c', cmd])


if __name__ == '__main__':
    # prep file
    logger = logging.getLogger('import_feeds')
    p = LogArgumentParser('import_feeds', 'import feeds.csv file')
    p.add_argument('input_file', metavar='INPUT_FILE')
    args = p.parse_args()

    logger.info("Feed Importer starting!")
    if len(sys.argv) != 2:
        logger.error("  You must supply a file to import from")
        sys.exit(1)
    filename = args.input_file
    logger.info("Importing from {}".format(filename))
    if filename.endswith(".gz"):
        import gzip
        f = gzip.open(filename)
    else:
        f = open(filename)
    # import data
    input_file = csv.DictReader(f)
    with engine.begin() as conn:  # will automatically close
        conn.execute(text("DELETE FROM feeds;"))
        conn.execute(text("DELETE FROM fetch_events;"))
        conn.execute(text("DELETE FROM stories;"))
    with Session() as session:
        for row in input_file:
            f = models.Feed(
                id=row['id'],
                url=row['url'],
                sources_id=row['sources_id'],
                name=row['name'],
                active=True,
                created_at=dt.datetime.now()
            )
            session.add(f)
        session.commit()
