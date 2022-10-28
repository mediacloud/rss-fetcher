"""
script invoked by run-fetch-rss-feeds.sh

When run with --loop, stays running as daemon,
sending queue stats, and refreshing the queue.
"""

import datetime as dt
import logging
import sys
import time
from typing import Any, List

# PyPI
from sqlalchemy import or_
from sqlalchemy.orm.query import Query
import sqlalchemy.sql.functions as f

# app
from fetcher.config import conf
from fetcher.database import engine, Session, SessionType
from fetcher.logargparse import LogArgumentParser
from fetcher.database.models import Feed, FetchEvent, utc
import fetcher.queue as queue
from fetcher.stats import Stats
import fetcher.tasks as tasks

SCRIPT = 'queue_feeds'          # NOTE! used for stats!
logger = logging.getLogger(SCRIPT)
stats = Stats.init(SCRIPT)


def queue_feeds(wq: queue.Queue, feed_ids: List[int], ts_iso: str) -> int:
    """
    Queue feeds, report stats and log.
    """
    queued = queue.queue_feeds(wq, feed_ids, ts_iso)
    total = len(feed_ids)
    # XXX report total-queued as separate (labled) counter?
    stats.incr('queued_feeds', queued)

    logger.info(f"Queued {queued}/{total} feeds")
    return queued


def find_and_queue_feeds(wq: queue.Queue, limit: int) -> int:
    """
    Find some active, undisabled, unqueued feeds
    that have not been checked, or are past due for a check (oldest first).
    """
    if limit > conf.MAX_FEEDS:
        limit = conf.MAX_FEEDS

    now = dt.datetime.utcnow()

    # Maybe order by (id % 100) instead of id
    #  to help break up clumps?
    with Session.begin() as session:  # type: ignore[attr-defined]
        # NOTE nulls_first is preferred in sqlalchemy 1.4
        #  but not available in sqlalchemy-stubs 0.4

        # maybe secondary order by (Feed.id % 1001)?
        #  would require adding adding a column to query
        rows = \
            _ready_ids(session)\
            .order_by(Feed.next_fetch_attempt.asc().nullsfirst(),
                      Feed.id.desc())\
            .limit(limit)\
            .all()  # all rows
        feed_ids = [row[0] for row in rows]
        if not feed_ids:
            return 0

        # mark as queued first so that workers can never see
        # a feed_id that hasn't been marked as queued.
        session.query(Feed)\
               .filter(Feed.id.in_(feed_ids))\
               .update({'last_fetch_attempt': now, 'queued': True},
                       synchronize_session=False)

        # create a fetch_event row for each feed:
        for feed_id in feed_ids:
            # created_at value matches Feed.last_fetch_attempt
            # (when queued) and queue entry
            session.add(
                FetchEvent.from_info(feed_id,
                                     FetchEvent.Event.QUEUED,
                                     now))
    return queue_feeds(wq, feed_ids, now.isoformat())


def _active_feed_ids(session: SessionType) -> Query:
    """
    base query to return active feed ids
    """
    return Feed._active_filter(session.query(Feed.id))


def count_active(session: SessionType) -> int:
    return _active_feed_ids(session).count()


def _ready_filter(q: Query) -> Query:
    return q.filter(Feed.queued.is_(False),
                    or_(Feed.next_fetch_attempt.is_(None),
                        Feed.next_fetch_attempt <= utc()))


def _ready_ids(session: SessionType) -> Query:
    """
    return base query for feed id's ready to be fetched
    """
    return _ready_filter(_active_feed_ids(session))


def loop(wq: queue.Queue, refill_period_mins: int) -> None:
    """
    Loop monitoring & reporting queue length to stats server

    Try to spread out load (smooth out any lumps),
    keeps queue short (db changes seen quickly)
    Initial randomization of next_fetch_attempt in import process
    will _initially_ avoid lumpiness, but downtime will cause
    pileups that will take at most MINIMUM_INTERVAL_MINS
    to clear (given enough workers).
    """

    logger.info(f"Starting loop: refill every {refill_period_mins} min")
    db_ready = hi_water = -1
    while True:
        t0 = time.time()        # wake time
        # logger.debug(f"top {t0}")

        # always report queue stats (inexpensive with rq):
        qlen = queue.queue_length(wq)     # queue(r) method??
        active = queue.queue_active(wq)   # jobs in progress
        workers = queue.queue_workers(wq)  # active workers

        # NOTE: initial qlen (not including added)
        #       active entries are NOT included in qlen
        stats.gauge('qlen', qlen)
        stats.gauge('active', active)
        stats.gauge('workers', workers)
        logger.debug(f"qlen {qlen} active {active} workers {workers}")

        added = 0

        # always queue on startup, then
        # wait for multiple of refill_period_mins.
        if (hi_water < 0 or
                (int(t0 / 60) % refill_period_mins) == 0):

            # name hi_water is a remnant of an implementation attempt
            # that refilled to hi_water only when queue drained to lo_water.

            # hi_water is the number of fetches per refill_period_mins
            # that need to be performed.  Enforcing this average means
            # that any "bunching" of ready feeds (due to outage) will
            # be spread out evenly.

            # Only putting as much work as needs to be done in
            # refill_period_mins means that database changes
            # (additions, enables, disables) can be seen quickly
            # rather than waiting for the whole queue to drain.

            with Session() as session:
                hi_water = tasks.fetches_per_minute(
                    session) * refill_period_mins

            # for dev/debug, on small databases:
            if hi_water < 10:
                hi_water = 10

            stats.gauge('hi_water', hi_water)

            # if queue is below the limit, fill up to the limit.
            if qlen < hi_water:
                added = find_and_queue_feeds(wq, hi_water - qlen)

        # gauges "stick" at last value, so always set:
        stats.gauge('added', added)

        # BEGIN MAYBE MOVE:
        # queries done once a minute for monitoring only!
        # if this is a problem move this section up
        # (under ... % refill_period_mins == 0)
        # statsd Gauges assume the value they are set to,
        # until they are set to a new value.

        # after find_and_queue_feeds, so does not include "added" entries
        with Session() as session:
            # all entries marked active and enabled.
            # there is probably a problem if more than a small
            #  fraction of active entries are ready!
            db_active = count_active(session)

            # should be approx (updated) qlen + active
            db_queued = session.query(Feed)\
                               .filter(Feed.queued.is_(True))\
                               .count()

            db_ready = _ready_ids(session).count()

        stats.gauge('db.active', db_active)
        stats.gauge('db.queued', db_queued)
        stats.gauge('db.ready', db_ready)

        logger.debug(
            f" db active {db_active} queued {db_queued} ready {db_ready}")
        # END MAYBE MOVE

        tnext = (t0 - t0 % 60) + 60  # top of the next minute after wake time
        t1 = time.time()
        s = tnext - t1             # sleep time
        if s > 0:
            # logger.debug(f"t1 {t1} tnext {tnext} sleep {s}")
            time.sleep(s)


if __name__ == '__main__':
    p = LogArgumentParser(SCRIPT, 'Feed Queuing')
    p.add_argument('--clear', action='store_true',
                   help='Clear queue and exit.')
    p.add_argument('--loop', metavar='M', type=int,
                   help='Clear queue and run as daemon, reporting stats, queuing feeds every M minutes.')
    p.add_argument('feeds', metavar='FEED_ID', nargs='*', type=int,
                   help='Fetch specific feeds')

    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    wq = queue.workq()

    if args.clear:
        logger.info("Clearing Queue")
        queue.clear_queue()
        sys.exit(0)

    if args.loop is not None:
        if args.feeds:
            logger.error('Cannot specify both --loop and feed ids')
            sys.exit(1)

        if args.loop < 1:
            logger.error('Cannot loop w/ interval less than 1 minute!')
            sys.exit(1)

        _ = conf.MAX_FEEDS      # force early logging
        logger.info("Clearing Queue")
        queue.clear_queue()

        loop(wq, args.loop)     # should never return
        sys.exit(1)             # should not get here

    # support passing in one or more feed ids on the command line
    if args.feeds:
        feed_ids = [int(feed) for feed in args.feeds]

        # validate ids:
        with Session() as session:
            rows = _active_feed_ids(session)\
                .filter(Feed.id.in_(feed_ids))\
                .all()
            valid_ids = [row[0] for row in rows]

        # maybe complain about invalid feeds??
        #   find via set(feed_ids) - set(valid_feeds)
        nowstr = dt.datetime.utcnow().isoformat()
        queue_feeds(wq, valid_ids, nowstr)
    else:
        # classic behavior (was run from cron every 30 min)
        # to restore, uncomment crontab entry in instance.sh
        # and remove --loop from Procfile
        find_and_queue_feeds(wq, conf.MAX_FEEDS)
