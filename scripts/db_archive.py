"""
top level script to archive and remove old database table entries
to prevent growth without bounds

NOTE! Output filenames contain time of script start;
does not indicate file contents

Media Cloud longer writing or archiving CSV files, so new StoryRef based
pruning does not write CSV files, and the name of this script is misleading!

Full database dumps are kept on cloud storage
"""

import csv
import datetime as dt
import gzip
import logging
import os.path

from sqlalchemy import delete, exists, func, select, text

import fetcher.path as path
from fetcher.config import conf
from fetcher.database import Session, engine, result_rowcount
from fetcher.database.models import Story, StoryRef
from fetcher.logargparse import LogArgumentParser

SCRIPT = 'db_archive'

logger = logging.getLogger(SCRIPT)


def logsize(fname: str) -> None:
    try:
        st = os.stat(fname)
        logger.info(f"{fname}: {st.st_size} bytes")
    except BaseException as e:
        logger.error(f"stat {fname}: {e}")


def dump_fetch_events(now: str, events: int, delete: bool, dump: bool) -> bool:
    """
    Write CSV file of fetch_events table
    keeping `events` table rows for each feed_id.
    """
    logger.info("creating temp table for ranking fetch_events")
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
        count = conn.scalar(text(f"SELECT COUNT(1) {from_temp_table}"))
        logger.info(f"found {count} fetch_events to archive/delete")
        if count == 0:
            return True

        # used for extract & deletion:
        from_where = f"FROM fetch_events WHERE id IN (SELECT id {from_temp_table})"

        if dump:
            query = f"SELECT * {from_where} ORDER BY id"
            logger.debug("%s", query)
            cursor = conn.execute(text(query))
            fname = os.path.join(path.DB_ARCHIVE_DIR,
                                 f"fetch_events-{now}.csv.gz")
            logger.info(f"writing {fname}")
            with gzip.open(fname, 'wt') as f:
                writer = csv.writer(f)
                first = next(cursor)._asdict()
                writer.writerow(first.keys())
                writer.writerow(first)
                writer.writerows(cursor)

        if delete:
            logger.info("deleting...")
            query = f"DELETE {from_where}"
            logger.debug("%s", query)
            conn.execute(text(query))

    if dump:
        logsize(fname)
    return True


def prune_stories(date_limit: dt.date, really_delete: bool) -> None:
    """
    prune stories last seen before date `limit`
    """

    with Session() as session:
        # prune expired refs
        where = StoryRef.seen_at < date_limit
        if really_delete:
            res = session.execute(delete(StoryRef).where(where))
            logger.info("deleted %d story_refs", result_rowcount(res))
        else:
            count = session.scalars(select(func.count())
                                    .select_from(StoryRef)
                                    .where(where)).one()
            logger.info("found %d story_refs to delete", count)

        # delete stories with no refs
        where = ~exists().where(StoryRef.story_id == Story.id)
        if really_delete:
            res = session.execute(delete(Story).where(where))
            logger.info("deleted %d stories", result_rowcount(res))
        else:
            count = session.scalars(select(func.count())
                                    .select_from(Story)
                                    .where(where)).one()
            logger.info("found %d stories to delete", count)

        # (no sources table in rss-fetcher)
        if really_delete:
            session.commit()


if __name__ == '__main__':
    p = LogArgumentParser(SCRIPT, 'prune stories and fetch_events tables')
    def_sd = max(conf.RSS_OUTPUT_DAYS, conf.NORMALIZED_TITLE_DAYS)
    p.add_argument('--story-days', type=int, default=def_sd,
                   help=f"number of days of story rows to keep ({def_sd})")
    def_fe = conf.FETCH_EVENT_ROWS
    p.add_argument('--fetch-events', type=int, default=def_fe,
                   help=f"number of fetch_events to keep per feed ({def_fe})")
    p.add_argument('--delete', action='store_true', default=False,
                   help="delete rows after writing files")
    p.add_argument('--dump', action='store_true', default=False,
                   help="create dump files (no longer archived)")
    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    now = dt.datetime.utcnow()
    date = now.strftime('%Y-%m-%d-%H-%M-%S')

    if args.dump and not os.path.isdir(path.DB_ARCHIVE_DIR):
        logger.info("Creating %s directory", path.DB_ARCHIVE_DIR)
        os.makedirs(path.DB_ARCHIVE_DIR)

    logger.info(f"Keeping {args.fetch_events} fetch_events for each feed")
    dump_fetch_events(date, args.fetch_events, args.delete, args.dump)

    logger.info(f"Keeping stories seen in the last %d days", args.story_days)
    limit = now.date() - dt.timedelta(days=args.story_days)
    # limit_str = limit.isoformat()
    prune_stories(limit, args.delete)
