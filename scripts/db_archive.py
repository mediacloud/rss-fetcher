"""
top level script to archive and remove old database table entries
to prevent growth without bounds

NOTE! Output filenames contain time of script start;
does not indicate file contents
"""

import csv
import datetime as dt
import gzip
import logging
import os.path
import subprocess

from sqlalchemy import text

from fetcher.config import conf
from fetcher.database import engine
from fetcher.logargparse import LogArgumentParser
import fetcher.path as path

SCRIPT = 'db_archive'

logger = logging.getLogger(SCRIPT)


def logsize(fname: str) -> None:
    try:
        st = os.stat(fname)
        logger.info(f"{fname}: {st.st_size} bytes")
    except BaseException as e:
        logger.error(f"stat {fname}: {e}")


def dump_fetch_events(now: str, events: int, delete: bool) -> bool:
    """
    Write CSV file of fetch_events table
    keeping `events` table rows for each feed_id.
    """
    logger.info("creating fetch_events temp table for ranking")
    with engine.begin() as conn:
        # create temp table (lasts as long as DB session)
        # with fetch_event row id and the row rank (n'th row)
        # within feed_id (older rows have higher rank).

        # This is necessary because:
        # 1. RANK cannot be used in a where clause
        # 2. There would be a race between new inserts and copy/delete.
        conn.execute(text(
            "SELECT id, RANK() OVER (PARTITION BY feed_id ORDER BY id DESC) AS rank INTO TEMP temp_table FROM fetch_events;"))

        # used for count, extraction, deletion:
        from_temp_table = f"FROM temp_table WHERE rank > {events}"

        logger.info("counting")
        count = conn.execute(
            text(f"SELECT COUNT(1) {from_temp_table}")).one()[0]
        logger.info(f"found {count} fetch_events to archive")
        if count == 0:
            return True

        # used for extract & deletion:
        from_where = f"FROM fetch_events WHERE id IN (SELECT id {from_temp_table})"

        cursor = conn.execute(text(f"SELECT * {from_where} ORDER BY id"))
        fname = os.path.join(path.DB_ARCHIVE_DIR, f"fetch_events-{now}.csv.gz")
        logger.info(f"writing {fname}")
        with gzip.open(fname, 'wt') as f:
            writer = csv.writer(f)
            first = next(cursor)
            writer.writerow(first.keys())
            writer.writerow(first)
            writer.writerows(cursor)

        if delete:
            logger.info("deleting...")
            conn.execute(text(f"DELETE {from_where}"))

    logsize(fname)
    return True


def dump_stories(now: str, limit: str, delete: bool) -> bool:
    """
    Write compressed csv file of stories table with fetched_at
    before `limit`
    """
    from_where = f"FROM stories WHERE fetched_at < '{limit}'"
    with engine.begin() as conn:
        logger.info("counting stories")
        count = conn.execute(text(f"SELECT COUNT(1) {from_where}")).one()[0]
        logger.info(f"found {count} stories to archive")
        if count == 0:
            return True

        cursor = conn.execute(
            text(f"SELECT * {from_where} ORDER BY fetched_at"))
        fname = os.path.join(path.DB_ARCHIVE_DIR, f"stories-{now}.csv.gz")
        logger.info(f"writing {fname}")
        with gzip.open(fname, 'wt') as f:
            writer = csv.writer(f)
            first = next(cursor)
            writer.writerow(first.keys())
            writer.writerow(first)
            writer.writerows(cursor)

        if delete:
            logger.info("deleting...")
            conn.execute(text(f"DELETE {from_where}"))

    logsize(fname)
    return True


if __name__ == '__main__':
    p = LogArgumentParser(SCRIPT, 'archive stories and fetch_events tables')
    def_sd = max(conf.RSS_OUTPUT_DAYS, conf.NORMALIZED_TITLE_DAYS)
    p.add_argument('--story-days', type=int, default=def_sd,
                   help=f"number of days of story rows to keep ({def_sd})")
    def_fe = conf.FETCH_EVENT_ROWS
    p.add_argument('--fetch-events', type=int, default=def_fe,
                   help=f"number of fetch_events to keep per feed ({def_fe})")
    p.add_argument('--delete', action='store_true', default=False,
                   help="delete rows after writing files")
    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    now = dt.datetime.utcnow()
    date = now.strftime('%Y-%m-%d-%H-%M-%S')

    dump_fetch_events(date, args.fetch_events, args.delete)

    limit = now.date() - dt.timedelta(days=args.story_days)
    limit_str = limit.isoformat()
    dump_stories(date, limit_str, args.delete)
