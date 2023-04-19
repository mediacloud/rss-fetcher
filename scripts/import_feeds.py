import csv
import datetime as dt
import logging
from random import random       # low-fi random ok

from sqlalchemy import text

from fetcher.config import conf
from fetcher.database import engine, Session
import fetcher.database.models as models
from fetcher.logargparse import LogArgumentParser


DEFAULT_INTERVAL_MINS = conf.DEFAULT_INTERVAL_MINS
SQLALCHEMY_DATABASE_URI = conf.SQLALCHEMY_DATABASE_URI

SCRIPT = 'import_feeds'


if __name__ == '__main__':
    # prep file
    logger = logging.getLogger(SCRIPT)
    p = LogArgumentParser(SCRIPT, 'import feeds.csv file')
    p.add_argument('--delete-stories', action='store_true')
    p.add_argument('--delete-fetch-events', action='store_true')

    # mandatory positional argument
    p.add_argument('input_file', metavar='INPUT_FILE')

    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message
    with engine.begin() as conn:  # will automatically close
        logger.info(f"Clearing feeds")
        conn.execute(text("DELETE FROM feeds;"))
        if args.delete_fetch_events:
            logger.info(f"Clearing fetch_events")
            conn.execute(text("DELETE FROM fetch_events;"))
        if args.delete_stories:
            logger.info(f"Clearing stories")
            conn.execute(text("DELETE FROM stories;"))

    # import data
    filename = args.input_file
    logger.info(f"Importing from {filename}")
    if filename.endswith(".gz"):
        import gzip
        f = gzip.open(filename, mode='rt')  # read in text mode
    else:
        f = open(filename)
    input_file = csv.DictReader(f)

    added = 0
    with Session.begin() as session:
        for row in input_file:
            now = dt.datetime.utcnow()
            # Pick random time within default fetch interval:
            # spreads out load, keeping queue short, and (hopefully)
            # avoiding hammering any site such that they give HTTP 429
            # (Too Many Requests) responses.
            next_fetch = now + \
                dt.timedelta(seconds=random() * DEFAULT_INTERVAL_MINS * 60)
            f = models.Feed(
                id=int(row['id']),
                url=row['url'],
                sources_id=int(row['sources_id']),
                name=row['name'],
                active=True,
                created_at=now,
                next_fetch_attempt=next_fetch
            )
            session.add(f)
            added += 1
        session.commit()
    logger.info(f"imported {added} rows")
