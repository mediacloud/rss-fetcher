"""
script invoked by run-fetch-rss-feeds.sh
"""

# XXX move all queries to models???

import datetime as dt
import logging
import sys
import time
from typing import List

# PyPI
from sqlalchemy import text, or_

# app
from fetcher import MAX_FEEDS, MINIMUM_INTERVAL_MINS
import fetcher.tasks as tasks
from fetcher.database import engine, Session
import fetcher.database.models as models
import fetcher.queue as queue
from fetcher.stats import Stats

logger = logging.getLogger('queue_feeds')

# Maximum times a day a feed can be fetched
# based on minimum allowed interval between fetches.
MAX_FETCHES_DAY = (24*60)/MINIMUM_INTERVAL_MINS

# Multiplier to estimated (necessary) per minute processing rate to
# get queue len low water mark (point at which refill occurs).
# Unless underpowered (too few workers), refills will likely occur
# more often.
REFILL_PERIOD_MINS = 5

# Multipler to low_water to for queue high water mark
# (the level to which the queue will be refilled).
HI_WATER_MULTIPLIER = 2

class Queuer:
    """
    class to encapsulate feed queuing.
    move some place public if needed elsewhere!
    """
    def __init__(self, stats, wq):
        self.stats = stats
        self.wq = wq


    def _active_feeds(self, session):
        """
        base query to return active feed id's
        """
        return session.query(models.Feed.id)\
                      .filter(models.Feed.active.is_(True),
                              models.Feed.system_enabled.is_(True))

    def count_active(self, session):
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
        if limit > MAX_FEEDS:
            limit = MAX_FEEDS

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

            # mark as queued first to avoid race with workers
            session.query(models.Feed)\
                   .filter(models.Feed.id.in_(feed_ids))\
                   .update({'last_fetch_attempt': now, 'queued': True},
                           synchronize_session=False)

            # create a fetch_event row for each feed:
            for feed_id in feed_ids:
                session.add(
                    models.FetchEvent.from_info(feed_id,
                                                models.FetchEvent.EVENT_QUEUED))
        return self.queue_feeds(feed_ids, now)

    def queue_feeds(self, feed_ids: List[int], ts: dt.datetime) -> int:
        queued = queue.queue_feeds(self.wq, feed_ids, ts)
        total = len(feed_ids)
        # XXX report total-queued as separate (labled) counter?
        self.stats.incr('queued_feeds', queued)

        logger.info(f"Queued {queued}/{total} feeds")
        return queued


# XXX make a queuer method? should only be used here!
def loop(queuer):
    """
    Loop monitoring & reporting queue length to stats server
    """

    low_water = None
    while True:
        # NOTE!! rate calculation will hickup if clock changed
        # (use time.monotonic() for rate calculation???)
        # but want wakeups at top of UTC minute!

        t0 = time.time()        # wake time
        #logger.debug(f"top {t0}")

        qlen = qlen0 = queue.queue_length(queuer.wq) # queue(r) method??

        if low_water is None or qlen < low_water:
            with Session.begin() as session:
                active = queuer.count_active(session)

            # The aim of this code is to keep a minimum number of
            # feeds in the work queue, so that changes (or additions)
            # to the database can take effect in close to real time.
            # `low_water` is work queue low water mark (refill below this number).
            # Calculated as the minimum number of feeds to fetch in order
            # to keep up if all feeds are fetched at the maximum allowed rate.
            # Unless we're underpowered (too few workers), refill interval will
            # likely be less than the target REFILL_PERIOD_MINS.
            low_water = round(active * MAX_FETCHES_DAY / 24 / 60 * REFILL_PERIOD_MINS)
            if low_water < 100:      # debug w/ small feeds database
                low_water = 100

        if qlen < low_water:
            # fill up to HI_WATER_MULTIPLIER*low_water
            added = queuer.find_and_queue_feeds(low_water*HI_WATER_MULTIPLIER - qlen)
            qlen = queue.queue_length(queuer.wq) # after find_and_queue_feeds
        else:
            added = 0

        queuer.stats.gauge('waiting', qlen0) # waiting in queue
        queuer.stats.gauge('low_water', low_water)
        queuer.stats.gauge('added', added)

        # jobs currently in process:
        active = queue.queue_active(queuer.wq)
        queuer.stats.gauge('active', active)

        #logger.debug(f"wait {qlen0} goal {low_water} added {added} active {active}")

        # queries done once a minute for graphs only!
        # (elininate, or do less frequently if a problem)
        with Session.begin() as session:
            db_queued = session.query(models.Feed)\
                               .filter(models.Feed.queued.is_(True))\
                               .count()

            db_ready = queuer._ready_query(session).count()

        # should be approx (updated) qlen + active
        queuer.stats.gauge('db.queued', db_queued)

        # remaining db entries available to be queued:
        queuer.stats.gauge('db.ready', db_ready)

        # figure out when to wake up next, prepare for bed.
        tnext = (t0 - t0%60) + 60  # top of minute after wake time
        t1 = time.time()
        s = tnext - t1             # sleep time
        if s > 0:
            #logger.debug(f"t1 {t1} tnext {tnext} sleep {s}")
            time.sleep(s)

if __name__ == '__main__':

    # XXX (call library to) parse options for log level?
    # shows generated SQL:
    #logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

    logger.info("Starting Feed Queueing")

    stats = Stats.init('queue_feeds')

    redis = queue.redis_connection()
    wq = queue.workq(redis)

    queuer = Queuer(stats, wq)

    # support passing in one or more feed ids on the command line
    if len(sys.argv) > 1:
        if sys.argv[1] == '--loop':
            sys.exit(loop(queuer))

        feed_ids = [int(id) for id in sys.argv[1:]] # positional args
        with Session.begin() as session:
            # validate ids
            valid_ids = queuer._ready_query(queuer)\
                              .filter(models.Feed.id.in_(feed_ids))\
                              .all()
        now = dt.datetime.utcnow()
        queuer.queue_feeds(valid_ids, now)
    else:
        queuer.find_and_queue_feeds(MAX_FEEDS)
