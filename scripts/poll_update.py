"""
top level script to set feed poll_minutes for feeds with small,
fixed size windows, that publish frequently
"""

import logging
import os.path

from sqlalchemy import select, update
from typing import List

from fetcher.database import Session
from fetcher.database.models import Feed, FetchEvent
from fetcher.stats import Stats

SCRIPT = 'poll_update'

logger = logging.getLogger(SCRIPT)


def feeds_to_update(rows: int, urls: int, fraction: float) -> List[int]:
    query = (select(FetchEvent.feed_id, FetchEvent.created_at, FetchEvent.note)  # type: ignore[arg-type]
             .where(FetchEvent.event == FetchEvent.Event.FETCH_SUCCEEDED.value)
             .order_by(FetchEvent.feed_id,
                       FetchEvent.created_at.desc()))
    # print(query)

    last_feed = -1
    to_update = []
    with Session() as session:
        for event in session.execute(query):
            feed = event.feed_id
            note = event.note
            created_at = event.created_at

            # ignore non-weekday rows
            if created_at.timetuple().tm_wday >= 5:  # monday is zero
                continue

            # print(feed, created_at, note)
            if feed != last_feed:  # new feed?
                n = 0
                matches = 0
                last_feed = feed
                urls_returned = -1
                candidate = True
                last = created_at  # most recent
                first = None       # earliest

            if not candidate:
                continue

            n += 1              # row count
            first = created_at  # earliest

            # ignore feed if not always skipped N / added N
            # (including "same hash" and "no change")
            # must ALWAYS have changed
            if not note.endswith('added'):
                candidate = False
                continue

            # ['30', 'skipped', '/', '0', 'added']
            toks = note.split()
            try:
                skipped = int(toks[0])
                added = int(toks[3])
            except BaseException:
                logger.warning(f"PARSE FAILED: {note}")
                continue

            total = skipped + added
            if urls_returned == -1:  # first time
                urls_returned = total

                # ignore feeds that ever return no URLs or too many
                if urls_returned >= URLS or urls_returned == 0:
                    candidate = False
                    continue
                # fall through for "matches" check

            if total != urls_returned:  # must always return same count
                candidate = False
                continue
            elif skipped == 0:
                matches += 1

            # could clear "candidate" once there are enough "misses"
            # so that feed couldn't be a candidate, perhaps
            # ((n-matches) > rows*(1-fraction))? but it's hardly
            # worth the effort.

            # print(feed, "n:", n, "matches:", matches)
            if n == rows:       # fetched enough data?
                # print(feed, matches / n, first, last)
                if matches / n >= fraction:
                    to_update.append(feed)
                    logger.debug(
                        f" adding {feed} ({matches}/{n} {first} {last})")
                candidate = False  # ignore remaining rows
                continue
    return to_update


def update_feeds(to_update: List[int], period: int) -> None:
    """
    just nail to a low value (could be made adaptive:
    starting period low, and and increasing?)
    """

    with Session() as session:
        u = (update(Feed)       # type: ignore[arg-type]
             .where(Feed.id.in_(to_update))
             .values(poll_minutes=period))
        res = session.execute(u)
        count = res.rowcount
        session.commit()
        logger.info(f"Updated {count} rows")
        stats = Stats.get()
        stats.incr('updated', count)


if __name__ == '__main__':
    from fetcher.logargparse import LogArgumentParser
    from fetcher.pidfile import LockedException, PidFile

    p = LogArgumentParser(SCRIPT, 'update feed poll_minutes column')
    p.add_argument('--update', action='store_true',
                   help="actually update date")
    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    # all could be command line options
    # (defaulted from config params):
    ROWS = 10                   # number of most recent rows to look at
    URLS = 100                  # too many urls returned
    FRACTION = 0.8              # fraction of ROWS that need to match
    PERIOD = 120                # update interval to set

    to_update = feeds_to_update(ROWS, URLS, FRACTION)
    logger.info(f"found {len(to_update)} feeds to update")

    if args.update and to_update:
        try:
            with PidFile(SCRIPT):
                update_feeds(to_update, PERIOD)
        except LockedException:
            logger.error("could not get lock")
            exit(255)
