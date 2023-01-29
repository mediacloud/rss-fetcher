"""
top level script to set feed poll_minutes for feeds with small,
fixed size windows, that publish frequently
"""

import logging
import os.path

from sqlalchemy import or_, select, update
from typing import List

from fetcher.config import conf
from fetcher.database import Session
from fetcher.database.models import Feed, FetchEvent
from fetcher.stats import Stats

SCRIPT = 'poll_update'

logger = logging.getLogger(SCRIPT)


def feeds_to_update(rows: int, urls: int, fraction: float,
                    reject_no_change: bool) -> List[int]:
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

            if not note.endswith('added'):
                if reject_no_change:
                    # ignore feed if not always skipped N / added N
                    # (including "same hash" and "no change")
                    # must ALWAYS have changed
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
                f = matches / n
                # print(feed, matches, n, f, first, last)
                if f >= fraction:
                    to_update.append(feed)
                    logger.debug(
                        f" adding {feed} ({matches}/{n} {first} {last})")
                candidate = False  # ignore remaining rows
                continue
    logger.info(f"found {len(to_update)} candidate feeds to update")
    return to_update


def update_feeds(to_update: List[int], period: int) -> None:
    """
    just nail to a low value (could be made adaptive:
    starting period low, and and increasing?)
    """

    with Session() as session:
        u = (update(Feed)       # type: ignore[arg-type]
             .where(Feed.id.in_(to_update))
             .where(or_(Feed.poll_minutes.is_(None),
                        Feed.poll_minutes > period))
             .values(poll_minutes=period))
        res = session.execute(u)
        count = res.rowcount
        session.commit()
        logger.info(f"Updated {count} rows")
        stats = Stats.get()
        stats.incr('updated', count)


if __name__ == '__main__':
    from argparse import ArgumentTypeError
    from sys import exit

    from fetcher.logargparse import LogArgumentParser
    from fetcher.pidfile import LockedException, PidFile

    # https://stackoverflow.com/questions/12116685/how-can-i-require-my-python-scripts-argument-to-be-a-float-in-a-range-using-arg
    def restricted_float(x: str) -> float:
        """test for float command line argument in range: 0.0 < x <= 1.0"""
        try:
            ret = float(x)
        except ValueError:
            raise ArgumentTypeError(f"{x!r} not a floating-point literal")

        if ret <= 0.0 or ret > 1.0:
            raise ArgumentTypeError(f"{ret!r} not in range (0.0, 1.0]")
        return ret

    # all could be command line options
    # (defaulted from config params):
    ROWS = 10                   # number of most recent rows to look at
    URLS = 100                  # too many urls returned
    PERIOD = conf.FAST_POLL_MINUTES  # update interval to set

    # default values:
    FRACTION = 0.8              # fraction of ROWS that need to match

    p = LogArgumentParser(SCRIPT, 'update feed poll_minutes column')
    # experiment:
    p.add_argument('--accept-no-change',
                   action='store_false', dest='reject_no_change',
                   help="consider feeds with 'no change' or 'same hash'")
    # current default:
    p.add_argument('--reject-no-change',
                   action='store_true', dest='reject_no_change',
                   help="reject feeds with 'no change' or 'same hash'")
    p.set_defaults(reject_no_change=True)

    p.add_argument('--fraction', type=restricted_float,
                   help=f"floating point (0,1] to fraction of fetches that must have no previously seen articles ({FRACTION})",
                   default=FRACTION)
    p.add_argument('--update', action='store_true',
                   help="actually update database (else just dry run)!")
    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    def get_feeds_to_update() -> List[int]:
        to_update = feeds_to_update(
            ROWS, URLS, args.fraction,
            reject_no_change=args.reject_no_change)
        return to_update

    if args.update:
        try:
            with PidFile(SCRIPT):
                to_update = get_feeds_to_update()
                update_feeds(to_update, PERIOD)
        except LockedException:
            logger.error("could not get lock")
            exit(255)
    else:
        logger.info(
            "DRY RUN! use --update to make changes: use -v to see candidates")
        get_feeds_to_update()
