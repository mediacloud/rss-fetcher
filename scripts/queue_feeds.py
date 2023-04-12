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
from fetcher.database import Session, SessionType
from fetcher.logargparse import LogArgumentParser
from fetcher.database.models import Feed, FetchEvent, utc
import fetcher.queue as queue
from fetcher.stats import Stats

SCRIPT = 'queue_feeds'          # NOTE! used for stats!
logger = logging.getLogger(SCRIPT)


def queue_feeds(session: SessionType,
                wq: queue.Queue,
                feed_ids: List[int],
                task_timeout: int,
                reset_next_attempt: bool = False) -> int:
    """
    Queue feeds, create FetchEvent rows, report stats and log.
    `session` should already be in a transaction!

    This is the ONLY place that should call queue.queue_feeds!!!
    If this is needed elsewhere move to a separate file!!!!!
    """
    stats = Stats.get()

    # XXX maybe break into batches (update now for each batch)
    # logging ids (@debug?) [and stats.incr for each batch?]

    # now timestamp used in:
    # * feed_worker queued args
    # * Feed.last_fetch attempt (must match above for sanity test)
    # * FetchEvent "queued" row
    now = dt.datetime.utcnow()
    nowstr = now.isoformat()

    updates = {
        'last_fetch_attempt': now,
        'queued': True
    }
    if reset_next_attempt:
        # process ASAP, always valid
        updates['next_fetch_attempt'] = None

    # mark as queued first so that workers can never see
    # a feed_id that hasn't been marked as queued.
    session.query(Feed)\
           .filter(Feed.id.in_(feed_ids))\
           .update(updates, synchronize_session=False)

    # create a fetch_event row for each feed:
    for feed_id in feed_ids:
        # created_at value matches Feed.last_fetch_attempt
        # (when queued) and queue entry
        session.add(
            FetchEvent.from_info(feed_id,
                                 FetchEvent.Event.QUEUED,
                                 now))

    queued = queue.queue_feeds(wq, feed_ids, nowstr, task_timeout)

    total = len(feed_ids)
    # XXX report total-queued as separate (labled) counter?
    stats.incr('queued_feeds', queued)

    logger.info(f"Queued {queued}/{total} feeds")

    return queued


def find_and_queue_feeds(wq: queue.Queue, limit: int, timeout: int) -> int:
    """
    Find some active, undisabled, unqueued feeds
    that have not been checked, or are past due for a check (oldest first).
    """
    with Session.begin() as session:  # type: ignore[attr-defined]
        # NOTE nulls_first is preferred in sqlalchemy 1.4
        #  but not available in sqlalchemy-stubs 0.4

        # XXX lock rows for update?

        # 2023-03-23: trying primary sort by poll_minutes, so fast
        # polling feeds go first (and avoid missing stories), this
        # should not (in theory) cause indefinite delay for slower
        # polling feeds, since fetches_per_minute query should
        # guarantee that there are enough queue "slots" for all feeds
        # (BUT it may mean that the auto-adjust code won't reset
        # poll_minutes back to "normal" if the feed is excessively
        # delayed), but it could lead to excessive delay. Perhaps
        # using `next_fetch_attempt + poll_minutes` for order would be
        # fairer (but handling NULLs might require coalesce function).

        rows = \
            _ready_ids(session)\
            .order_by(Feed.poll_minutes.asc().nullslast(),
                      Feed.next_fetch_attempt.asc().nullsfirst(),
                      (Feed.id % 1001).desc())\
            .limit(limit)\
            .all()  # all rows
        feed_ids = [row[0] for row in rows]
        if not feed_ids:
            return 0

        ret = queue_feeds(session, wq, feed_ids, timeout)
        session.commit()
        return ret


def _active_feed_ids(session: SessionType) -> Query:
    """
    base query to return active feed ids
    """
    return Feed._active_filter(session.query(Feed.id))


def count_active(session: SessionType) -> int:
    return _active_feed_ids(session).count()


def count_queued(session: SessionType) -> int:
    return session.query(Feed)\
                  .filter(Feed.queued.is_(True))\
                  .count()


def _ready_filter(q: Query) -> Query:
    return q.filter(Feed.queued.is_(False),
                    or_(Feed.next_fetch_attempt.is_(None),
                        Feed.next_fetch_attempt <= utc()))


def _ready_ids(session: SessionType) -> Query:
    """
    return base query for feed id's ready to be fetched
    """
    return _ready_filter(_active_feed_ids(session))


def _stray_catcher(task_timeout: int) -> int:
    """
    "stray feed catcher"

    Here in refill_period_mins check, when qlen == 0
    """
    with Session() as session:
        db_queued = count_queued(session)
        if db_queued == 0:
            return 0

        # here if queue empty, but there db entries marked queued;
        # clear "queued" column on any entry "started" a while ago
        logger.debug(f"stray_catcher found {db_queued} queued feed(s)")

        # last_fetch_attempt is set when the feed is queued,
        # and updated when the feed is picked up from the queue
        # by a worker (and is no longer in queue); wait a small
        # multiple of the job timeout before declaring "stray"
        # (so we're safe, even if the DB entry didn't get updated):
        a_while_ago = dt.datetime.utcnow() - dt.timedelta(seconds=5 * task_timeout)
        reset_count = \
            session.query(Feed)\
            .filter(Feed.queued.is_(True),
                    Feed.last_fetch_attempt < a_while_ago)\
            .update({'queued': False},
                    synchronize_session=False)
        session.commit()
        if reset_count:
            logger.warning(
                f"qlen = 0; stray_catcher reset {reset_count} queued feed(s)")
        return int(reset_count or 0)


def loop(wq: queue.Queue, refill_period_mins: int,
         task_timeout: int, max_feeds: int) -> None:
    """
    Loop monitoring & reporting queue length to stats server

    Try to spread out load (smooth out any lumps),
    keeps queue short (db changes seen quickly)
    Initial randomization of next_fetch_attempt in import process
    will _initially_ avoid lumpiness, but downtime will cause
    pileups that will take at most MINIMUM_INTERVAL_MINS
    to clear (given enough workers).
    """

    stats = Stats.get()

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

        # wait for multiple of refill_period_mins.
        if (int(t0 / 60) % refill_period_mins) == 0:
            if qlen == 0:
                strays = _stray_catcher(task_timeout)
            else:
                strays = 0
            stats.gauge('strays_caught', strays)

            # The name hi_water is a remnant of an implementation
            # attempt that refilled to the queue hi_water only when
            # queue was below lo_water.

            # hi_water is now the number of fetches per refill_period_mins
            # that need to be performed to get through all the feeds
            # in a timely manner (ie; keep our head above water).

            # Only queuing as much work as needs to be done in
            # refill_period_mins means that database changes
            # (additions, enables, disables) can be seen quickly
            # rather than waiting for the whole queue to drain.

            # When restarting after down time, there will be a backlog
            # of "ready" feeds, which will slowly go down (processed
            # in the same order they would have been, just delayed).

            # There will be natural "slosh" of feeds between
            # refill_period_mins intervals due to error backoffs and
            # the hi_water mark going down as feeds are disabled due
            # to errors.

            ohw = hi_water
            with Session() as session:
                hi_water = round(
                    tasks.fetches_per_minute(session) *
                    refill_period_mins)

            # for dev/debug, on small databases:
            if hi_water < 10:
                hi_water = 10

            stats.gauge('hi_water', hi_water)

            if hi_water != ohw:
                logger.info(f"queue goal {hi_water}")

            # if queue is below the limit, fill up to the limit.
            if qlen < hi_water:
                limit = hi_water - qlen
                if limit > max_feeds:
                    limit = max_feeds
                added = find_and_queue_feeds(wq, hi_water - qlen, task_timeout)

        # gauges "stick" at last value, so always set:
        stats.gauge('added', added)

        stats.incr('added2', added)

        # queries done once a minute for monitoring only!
        # statsd Gauges assume the value they are set to,
        # until they are set to a new value, so when this process
        # exits, the values will stick.

        # after find_and_queue_feeds, so does not include "added" entries
        with Session() as session:
            # all entries marked active and enabled.
            db_active = count_active(session)

            # should be approx (updated) qlen + active
            db_queued = count_queued(session)
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
    # XXX maybe add --monitor (loop monitoring, but not queuing)???

    # XXX maybe make command line arguments??
    task_timeout = conf.TASK_TIMEOUT_SECONDS
    max_feeds = conf.MAX_FEEDS

    p = LogArgumentParser(SCRIPT, 'Feed Queuing')
    p.add_argument('--clear', action='store_true',
                   help='Clear queue and exit.')
    p.add_argument('--fetches-per-minute', action='store_true',
                   help='Display calculated fetches per minute and exit.')
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

        logger.info("Clearing Queue")
        queue.clear_queue()

        loop(wq, args.loop, task_timeout, max_feeds)  # should never return
        sys.exit(1)             # should not get here

    # support passing in one or more feed ids on the command line
    if args.feeds:
        # (NOTE: no enforcement of max_feeds!)
        feed_ids = [int(feed) for feed in args.feeds]

        # validate ids:
        with Session() as session:
            rows = _active_feed_ids(session)\
                .filter(Feed.id.in_(feed_ids))\
                .all()
            valid_ids = [row[0] for row in rows]

        # log how many are valid:
        if len(valid_ids) != len(feed_ids):
            logger.info(f" {len(valid_ids)}/{len(feed_ids)} valid feeds")

        with Session() as session, session.begin():
            queue_feeds(
                session,
                wq,
                valid_ids,
                task_timeout,
                reset_next_attempt=True)

    else:
        # classic behavior (run from cron every 30 min)
        # remove --loop from Procfile
        # and re-run instance.sh (replacing crontab)
        find_and_queue_feeds(wq, max_feeds, task_timeout)
