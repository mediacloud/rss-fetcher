"""
script invoked by run-fetch-rss-feeds.sh
"""

import datetime as dt
import logging
import sys
import time
from typing import List

# PyPI
from sqlalchemy import text, or_

# app
from fetcher import MAX_FEEDS
import fetcher.tasks as tasks
from fetcher.database import engine, Session
import fetcher.database.models as models
import fetcher.queue as queue
from fetcher.stats import Stats

logger = logging.getLogger(__name__)

class Queuer:
    """
    class to encapsulate feed queuing.
    move some place public if needed elsewhere!
    """
    def __init__(self, stats, wq):
        self.stats = stats
        self.wq = wq


    def find_and_queue_feeds(self, limit: int) -> int:
        """
        Find some active, undisabled, unqueued feeds
        that have not been checked, or are past due for a check (oldest first).
        """
        if limit > MAX_FEEDS:
            limit = MAX_FEEDS

        with Session.begin() as session:
            ready = session.query(models.Feed.id)\
                           .filter(models.Feed.active.is_(True),
                                   models.Feed.system_enabled.is_(True),
                                   models.Feed.queued.is_(False),
                                   or_(models.Feed.next_fetch_attempt.is_(None),
                                       models.Feed.next_fetch_attempt <= models.utc()))

            rows = ready.order_by(models.Feed.next_fetch_attempt.asc().nulls_first(),
                                  models.Feed.id.desc())\
                        .limit(limit)\
                        .all()  # all rows
            feed_ids = [row[0] for row in rows]

            # mark as queued first to avoid race with workers
            now = dt.datetime.utcnow()

            # mark each row in feed_ids as queued, and mark start time
            session.query(models.Feed)\
                   .filter(models.Feed.id.in_(feed_ids))\
                   .update({'last_fetch_attempt': now, 'queued': True},
                           synchronize_session=False)

            # create a fetch_event row for each feed:
            for feed_id in feed_ids:
                session.add(
                    models.FetchEvent.from_info(feed_id,
                                                models.FetchEvent.EVENT_QUEUED))

            all_ready = ready.count()
            logger.info("all_ready {all_ready}") # XXX report as gauge

        # XXX return all_ready??
        return self.queue_feeds(feed_ids)


    def queue_feeds(self, feed_ids: List[int]) -> int:
        queued = queue.queue_feeds(self.wq, feed_ids)

        # XXX compare queued w/ len(feed_ids) and complain if not equal??
        # XXX report unqueued as separate (labled) counter?

        self.stats.incr('queued_feeds', queued)

        total = len(feed_ids)
        logger.info(f"  queued {queued}/{total} feeds")
        self.log_reg_counts()   # TEMP

        return queued


    def log_reg_counts(self):   # TEMP
        logger.info(f"  reg_counts {queue.reg_counts(self.wq)}")


# XXX make a queuer method? should only be used here!
def loop(queuer):
    """
    Loop monitoring & reporting queue length to stats server
    """
    # `rates` has the last `MAX_RATES` one-minute work queue consumption rates
    # averaged to get estimated burn rate.

    # "goal" is the average of rates entries times GOAL_MINUTES
    # when queue length falls below goal/2 (low water mark),
    # goal-qlen entries are added to refill (to the high water mark).

    old_qlen = old_time = None
    MINQ = 100       # lower limit for queue length goal
    rates = [MINQ]
    MAX_RATES = 5    # number of samples to keep in rates list
    GOAL_MINUTES = 5 # number of minutes of work to try to keep queued (must be > 1!!)
    LOW_RATE = MINQ/GOAL_MINUTES # lower bound for acceptable rate

    while True:
        # NOTE!! rate calculation will hickup if clock changed
        # (use time.monotonic() for rate calculation???)
        # but want wakeups at top of UTC minute

        t0 = time.time()
        logger.debug(f"top {t0}")

        qlen = queue.queue_length(queuer.wq) # queue(r) method??
        queuer.log_reg_counts()              # TEMP

        # try to update processing rate
        if old_qlen is not None and old_time is not None:
            delta_qlen = old_qlen - qlen
            delta_t = (t0 - old_time) / 60 # minutes

            if delta_t > 0.5 and delta_qlen > 0:
                r = delta_qlen / delta_t
                logger.info(f"r {r} ({delta_qlen} / {delta_t})")
                if r < LOW_RATE:
                    r = LOW_RATE
                # keep last N samples
                rates.append(r)
                if len(rates) > MAX_RATES:
                    rates.pop(0)

        # calculate rate over N minutes
        rate = sum(rates) / len(rates)
        goal = round(rate * GOAL_MINUTES)
        if goal > MAX_FEEDS:
            goal = MAX_FEEDS
        logger.info(f"qlen {qlen} rate {rate} goal {goal}")
        if qlen < goal/2:       # less than half full?
            queuer.find_and_queue_feeds(goal-qlen) # top off queue
            qlen = queue.queue_length(queuer.wq) # after find_and_queue_feeds

        tnext = (t0 - t0%60) + 60  # top of minute after wake time
        old_time = t1 = time.time()
        old_qlen = qlen

        s = tnext - t1             # time until then to sleep
        if s > 0:
            logger.debug(f"t1 {t1} tnext {tnext} sleep {s}")
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
        # XXX validate ids?
        queuer.queue_feeds(feed_ids)
    else:
        queuer.find_and_queue_feeds(MAX_FEEDS)
