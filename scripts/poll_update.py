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


def update_feeds(rows: int,     # need to see this many successes
                 urls: int,
                 fraction: float,  # fraction of fetches to qualify min: 1/rows, max 1
                 reject_no_change: bool,  # don't consider feeds that didn't change
                 update: bool,  # actually update rows
                 period: int    # period in minutes to set poll_minutes to
                 ) -> None:

    stats = Stats.get()

    query = (select(FetchEvent.feed_id, FetchEvent.created_at, FetchEvent.note)  # type: ignore[arg-type]
             .where(FetchEvent.event == FetchEvent.Event.FETCH_SUCCEEDED.value)
             .order_by(FetchEvent.feed_id,
                       FetchEvent.created_at.desc()))
    # print(query)

    last_feed = -1
    rows = count = dup = skipped = skipped_feeds = 0
    with Session() as session:
        for event in session.execute(query):
            rows += 1
            feed_id = event.feed_id
            note = event.note
            created_at = event.created_at

            # ignore non-weekday rows
            if created_at.timetuple().tm_wday >= 5:  # monday is zero
                continue

            # print(feed_id, created_at, note)
            if feed_id != last_feed:  # new feed?
                n = 0
                matches = 0
                last_feed = feed_id
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
            # ['0', 'skipped', '/', '30', 'dup', '/', '0', 'added']
            toks = note.split()
            try:
                if len(toks) == 5:
                    dup = int(toks[0])  # (skipped)
                    added = int(toks[3])
                    total = dup + added
                else:
                    skipped = int(toks[0])
                    dup = int(toks[3])
                    added = int(toks[6])
                    total = skipped + dup + added
            except BaseException:
                logger.warning(f"PARSE FAILED: {note}")
                continue

            if urls_returned == -1:  # first time
                urls_returned = total

                # ignore feeds that ever return no URLs or too many
                if urls_returned >= urls or urls_returned == 0:
                    candidate = False
                    continue
                # fall through for "matches" check

            if total != urls_returned:  # must always return same count
                candidate = False
                continue
            elif dup == 0:
                matches += 1

            # could clear "candidate" once there are enough "misses"
            # so that feed couldn't be a candidate, perhaps
            # ((n-matches) > rows*(1-fraction))? but it's hardly
            # worth the effort.

            # print(feed_id, "n:", n, "matches:", matches)
            if n == rows:       # fetched enough data?
                f = matches / n
                # print(feed_id, matches, n, f, first, last)
                if f >= fraction:
                    feed_obj = session.get(Feed, feed_id)
                    if feed_obj.poll_minutes is None or feed_obj.poll_minutes > period:
                        # used to display {first} {last} (date times, but not
                        # that valuable)
                        logger.debug(
                            f" {feed_id} ({matches}/{n} {urls_returned} {feed_obj.update_minutes})")
                        if update:
                            # XXX if feed_obj.update_minutes is not None, use
                            # max(update_minutes, period)?
                            feed_obj.poll_minutes = period
                            session.add(feed_obj)
                            stats.incr('updated', count)
                        count += 1
                    else:
                        skipped_feeds += 1
                candidate = False  # ignore remaining rows
                continue
        # end for
        logger.info(f"processed {rows} events")
        logger.info(f"found {count} feeds to update, skipped {skipped_feeds}")
        if update:
            session.commit()

    # end session


if __name__ == '__main__':
    from argparse import ArgumentTypeError
    import sys

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
    PERIOD = conf.FAST_POLL_MINUTES  # update interval to set

    # default values (could fetch from config!)
    FETCHES = 10               # number of most recent rows to look at
    FRACTION = 0.8             # fraction of ROWS that need to match
    MAX_URLS = 100             # too many urls returned

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

    p.add_argument('--fetches', type=int,
                   help=f"number of successful fetches required (default: {FETCHES})",
                   default=FETCHES)
    p.add_argument('--fraction', type=restricted_float,
                   help=f"floating point (0,1] to fraction of fetches that must have no previously seen articles ({FRACTION})",
                   default=FRACTION)
    p.add_argument('--max-urls', type=int,
                   help=f"maximum URLs returned (default: {MAX_URLS})",
                   default=MAX_URLS)
    p.add_argument('--update', action='store_true',
                   help="actually update database (else just dry run)!")
    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    def do_update() -> None:
        if args.max_urls < 1:
            logger.warning("--max-urls must be >= 1")
            sys.exit(1)

        if args.fetches < 1:
            logger.warning("--fetches must be >= 1")
            sys.exit(1)

        update_feeds(
            args.fetches, args.max_urls, args.fraction,
            reject_no_change=args.reject_no_change,
            update=args.update,
            period=PERIOD
        )

    if args.update:
        try:
            with PidFile(SCRIPT):
                do_update()
        except LockedException:
            logger.error("could not get lock")
            sys.exit(255)
    else:
        logger.info(
            "DRY RUN! use --update to make changes: use -v to see candidates")
        do_update()
