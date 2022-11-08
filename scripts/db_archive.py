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
from fetcher.database.models import FetchEvent
from fetcher.logargparse import LogArgumentParser
import fetcher.path as path

SCRIPT = 'db_archive'

logger = logging.getLogger(SCRIPT)

SQLALCHEMY_DATABASE_URI = conf.SQLALCHEMY_DATABASE_URI


def logsize(fname: str) -> None:
    try:
        st = os.stat(fname)
        logger.info(f"{fname}: {st.st_size} bytes")
    except BaseException as e:
        logger.error(f"stat {fname}: {e}")


def runlog(*cmdline) -> bool:
    """
    run command; log stdout/err
    """
    # capture stdout/stderr to one string
    # NOTE! shell=False make safer (args not evaluated by shell)
    ret = subprocess.run(
        cmdline,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False)
    for line in ret.stdout.decode('utf-8').split('\n'):
        if line:
            logger.info(f"{cmdline[0]}: {line}")
    return ret.returncode == 0


def dump_fetch_events(now: str, events: int, delete: bool) -> bool:
    """
    Write CSV file of fetch_events table
    keeping `events` table rows for each feed_id.
    """
    with engine.begin() as conn:
        # create temp table (lasts as long as DB session)
        # with fetch_event row id and the row rank (n'th row)
        # within feed_id (older rows have higher rank).

        # This is necessary because:
        # 1. RANK cannot be used in a where clause
        # 2. There would be a race between new inserts and copy/delete.
        conn.execute(text(
            "SELECT id, RANK() OVER (PARTITION BY feed_id ORDER BY id DESC) AS rank INTO TEMP ttt FROM fetch_events;"))

        # could also delete rows to keep
        # (rank <= fetch_events) from temp table!
        where = f"id in (SELECT id FROM ttt WHERE rank > {events})"
        cursor = conn.execute(text(
            f"SELECT * FROM fetch_events WHERE {where} ORDER BY id"))

        fname = os.path.join(path.DB_ARCHIVE_DIR, f"fetch_events.{now}.gz")
        fields = [col.name for col in FetchEvent.__mapper__.columns]
        with gzip.open(fname, 'wt') as f:
            writer = csv.writer(f)
            writer.writerow(fields)
            writer.writerows(cursor)

        if delete:
            conn.execute(text(f"DELETE FROM fetch_events WHERE {where}"))

    logsize(fname)
    return True


def dump(table: str, where: str, now: str, delete: bool) -> bool:
    path.check_dir(path.DB_ARCHIVE_DIR)
    fname = os.path.join(path.DB_ARCHIVE_DIR, f"{table}.{now}")
    with open(fname, "wb") as output:
        logger.info(f"output to {fname}")

        sql = f"SELECT * FROM {table} WHERE {where};"
        logger.debug(f"SQL: {sql}")
        # XXX create pipeline: psql | gzip > fname?
        # XXX capture stderr & log??
        ret = subprocess.run(
            ['psql', '--csv', SQLALCHEMY_DATABASE_URI, '-c', sql],
            shell=False,        # for safety
            stdout=output)
        logger.debug(f"return code {ret.returncode}")
        logsize(fname)

    if ret.returncode != 0:
        logger.error(sql)
        return False

    if not runlog('gzip', '-fv', fname):
        return False
    logsize(fname + '.gz')

    if not delete:
        return True

    sql = f"DELETE FROM {table} WHERE {where};"
    logger.debug(f"SQL: {sql}")
    return runlog('psql', SQLALCHEMY_DATABASE_URI, '-c', sql)


if __name__ == '__main__':
    p = LogArgumentParser(SCRIPT, 'archive stories and fetch_events tables')
    p.add_argument('--story-days', type=int, default=conf.RSS_OUTPUT_DAYS,
                   help="number of days of stories table rows to keep")
    p.add_argument('--fetch-events', type=int, default=conf.FETCH_EVENT_ROWS,
                   help="number of fetch_events rows to keep for each feed")
    p.add_argument('--delete', action='store_true', default=False,
                   help="delete rows after writing files")
    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    now = dt.datetime.utcnow()
    fname = now.strftime('%Y-%m-%d-%H-%M-%S')

    dump_fetch_events(fname, args.fetch_events, args.delete)

    limit = now.date() - dt.timedelta(days=args.story_days)
    limit_str = limit.isoformat()
    dump('stories', f"fetched_at < '{limit_str}'", fname, args.delete)
