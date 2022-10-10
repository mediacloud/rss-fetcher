import logging
import datetime as dt
from random import random       # low-fi random ok
import sys
from subprocess import call
import os
import csv

from sqlalchemy import text

from fetcher import DEFAULT_INTERVAL_MINS
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
            now = dt.datetime.utcnow()
            # Pick random time within default fetch interval to
            # spreads out load, keeping queue short, and avoiding
            # hammering any site such that they give HTTP 429 
            # (Too Many Requests) responses.
            next_fetch = now + timedelta(seconds=random()*DEFAULT_INTERVAL_MINS*60)
            f = models.Feed(
                id=row['id'],
                url=row['url'],
                sources_id=row['sources_id'],
                name=row['name'],
                active=True,
                created_at=now,
                next_fetch_attempt=next_fetch
            )
            session.add(f)
        session.commit()
