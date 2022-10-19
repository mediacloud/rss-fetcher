"""
script invoked by run-fetch-rss-feeds.sh

When run with --loop, stays running as daemon,
sending queue stats, and refreshing the queue.
"""

import datetime as dt
import logging
import sys
import time
from typing import List

# PyPI
from sqlalchemy import or_

# app
from fetcher.config import conf
from fetcher.database import engine, Session
from fetcher.logargparse import LogArgumentParser
import fetcher.database.models as models
import fetcher.queue as queue
from fetcher.stats import Stats
import fetcher.tasks as tasks

SCRIPT = 'queue_feeds'          # NOTE! used for stats!
logger = logging.getLogger(SCRIPT)


class Queuer:
    """
    class to encapsulate feed queuing.
    move some place public if needed elsewhere!
    """

    def __init__(self, stats, wq):
        self.stats = stats
        self.wq = wq
        _ = conf.MAX_FEEDS  # log early

    def _active_feeds(self, session, full=False):
        """
        base query to return active feeds
        """
        if full:
            q = models.Feed
        else:
            q = models.Feed.id
        return session.query(q)\
                      .filter(models.Feed.active.is_(True),
                              models.Feed.system_enabled.is_(True))

    def count_active(self, session) -> int:
        return self._active_feeds(session).count()

    def _ready_query(self, session):
        """
        return base query for feed id's ready to be fetched
        """
        return self._active_feeds(session)\
                   .filter(models.Feed.queued.is_(False),
                           or_(models.Feed.next_fetch_attempt.is_(None),
                               models.Feed.next_fetch_attempt <= models.utc()))

    def find_and_queue_feeds(self, limit: int) -> int:
        """
        Find some active, undisabled, unqueued feeds
        that have not been checked, or are past due for a check (oldest first).
        """
        if limit > conf.MAX_FEEDS:
            limit = conf.MAX_FEEDS

        now = dt.datetime.utcnow()
        with Session.begin() as session:
            rows = self._ready_query(session)\
                       .order_by(models.Feed.next_fetch_attempt.asc().nulls_first(),
                                 models.Feed.id.desc())\
                       .limit(limit)\
                       .all()  # all rows
            feed_ids = [row[0] for row in rows]
            if not feed_ids:
                return 0

            # mark as queued first so that workers can never see
            # a feed_id that hasn't been marked as queued.
            session.query(models.Feed)\
                   .filter(models.Feed.id.in_(feed_ids))\
                   .update({'last_fetch_attempt': now, 'queued': True},
                           synchronize_session=False)

            # create a fetch_event row for each feed:
            for feed_id in feed_ids:
                # use "now" for FetchEvent created_at?
                session.add(
                    models.FetchEvent.from_info(feed_id,
                                                models.FetchEvent.Event.QUEUED))
        return self.queue_feeds(feed_ids, now.isoformat())

    def queue_feeds(self, feed_ids: List[int], ts_iso: str) -> int:
        queued = queue.queue_feeds(self.wq, feed_ids, ts_iso)
        total = len(feed_ids)
        # XXX report total-queued as separate (labled) counter?
        self.stats.incr('queued_feeds', queued)

        logger.info(f"Queued {queued}/{total} feeds")
        return queued


# XXX make a queuer method? should only be used here!
def loop(queuer) -> None:
    """
    Loop monitoring & reporting queue length to stats server
    """

    # Try to spread out load (smooth out any lumps),
    # keeps queue short (db changes seen quickly)
    # Initial randomization of next_fetch_attempt in import process
    # will _initially_ avoid lumpiness, but downtime will cause
    # pileups that will take at most MINIMUM_INTERVAL_MINS
    # to clear (given enough workers).

    # how often to refill queue (take as argument to --loop?)
    refill_period_mins = 5      # XXX config param?

    # log early
    _ = conf.MINIMUM_INTERVAL_MINS

    logger.info(f"Starting loop: refill every {refill_period_mins} min")
    db_ready = hi_water = -1
    while True:
        t0 = time.time()        # wake time
        # logger.debug(f"top {t0}")

        qlen = queue.queue_length(queuer.wq)  # queue(r) method??
        active = queue.queue_active(queuer.wq)  # jobs in progress

        # NOTE: initial qlen (not including added)
        #       active entries NOT included in qlen
        queuer.stats.gauge('qlen', qlen)
        queuer.stats.gauge('active', active)
        logger.debug(f"qlen {qlen} active {active}")

        with Session.begin() as session:
            # all entries marked active and enabled.
            # there is probably a problem if more than a small
            #  fraction of active entries are ready!
            db_active = queuer.count_active(session)

        added = 0

        # always refill on restart, or when there is a backlog.
        if (hi_water < 0 or db_ready > hi_water or
                (int(t0 / 60) % refill_period_mins) == 0):
            # Put enough into queue to handle all active feeds
            # polled at MINIMUM_INTERVAL_MINS.  So far, an adaptive
            # solution to estimate the run-rate, has been illusive
            # (estimates were noisy, and code bulky).
            hi_water = round(
                refill_period_mins *
                db_active /
                conf.MINIMUM_INTERVAL_MINS)

            # for dev/debug, avoid underflow on small databases:
            if hi_water < 10:
                hi_water = 10

            # if queue is below the limit, fill up to the limit.
            if qlen < hi_water:
                added = queuer.find_and_queue_feeds(hi_water - qlen)
        queuer.stats.gauge('added', added)

        # begin maybe move
        # queries done once a minute for monitoring only!
        # if this is a problem move this section up
        # (under ... % refill_period_mins == 0)
        # statsd Gauges assume the value they are set to,
        # until they are set to a new value.

        # after find_and_queue_feeds, so does not include "added" entries
        with Session.begin() as session:
            # should be approx (updated) qlen + active
            db_queued = session.query(models.Feed)\
                               .filter(models.Feed.queued.is_(True))\
                               .count()

            db_ready = queuer._ready_query(session).count()

        queuer.stats.gauge('db.active', db_active)
        queuer.stats.gauge('db.queued', db_queued)
        queuer.stats.gauge('db.ready', db_ready)

        logger.debug(
            f" db_active {db_active} db_queued {db_queued} db_ready {db_ready}")
        # end maybe move

        # figure out when to wake up next, prepare for bed.
        tnext = (t0 - t0 % 60) + 60  # top of minute after wake time
        t1 = time.time()
        s = tnext - t1             # sleep time
        if s > 0:
            # logger.debug(f"t1 {t1} tnext {tnext} sleep {s}")
            time.sleep(s)


if __name__ == '__main__':
    p = LogArgumentParser(SCRIPT, 'Feed Queuing')
    p.add_argument('--clear', action='store_true',
                   help='Clear queue first.')
    p.add_argument('--loop', action='store_true',
                   help='Run as daemon, sending stats (implies --clear)')
    p.add_argument('feeds', metavar='FEED_ID', nargs='*', type=int,
                   help='Fetch specific feeds')

    # info logging before this call unlikely to be seen:
    args = p.parse_args()       # parse logging args, output start message

    stats = Stats.init(SCRIPT)

    wq = queue.workq()

    queuer = Queuer(stats, wq)

    if args.clear or args.loop:
        logger.info("Clearing Queue")
        queue.clear_queue()

    if args.loop:
        if args.feeds:
            logger.error('Cannot give both --loop and feed ids')
            sys.exit(1)
        sys.exit(loop(queuer))

    # support passing in one or more feed ids on the command line
    if args.feeds:
        feed_ids = [int(feed) for feed in args.feeds]
        with Session.begin() as session:
            # validate ids
            rows = queuer._ready_query(session)\
                         .filter(models.Feed.id.in_(feed_ids))\
                         .all()
            valid_ids = [row[0] for row in rows]
        # maybe complain about invalid feeds??
        #   find via set(feed_ids) - set(valid_feeds)
        nowstr = dt.datetime.utcnow().isoformat()
        queuer.queue_feeds(valid_ids, nowstr)
    else:
        # classic behavior (was run from cron every 30 min)
        # to restore, uncomment crontab entry in instance.sh
        # and remove --loop from Procfile
        queuer.find_and_queue_feeds(conf.MAX_FEEDS)
