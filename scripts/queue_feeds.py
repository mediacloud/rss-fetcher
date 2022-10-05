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


class Queuer:
    """
    class to encapsulate feed queuing.
    move some place public if needed elsewhere!
    """
    def __init__(self, stats, wq, logger):
        self.stats = stats
        self.wq = wq
        self.logger = logger


    def find_and_queue_feeds(self, limit: int) -> int:
        """
        Find some active, undisabled, unqueued feeds
        that have not been checked, or are past due for a check (oldest first).
        """
        with Session.begin() as session:
            ready = session.query(models.Feed.id)\
                           .filter(models.Feed.active.is_(True),
                                   models.Feed.system_enabled.is_(True),
                                   models.Feed.queued.is_(False),
                                   or_(models.Feed.next_fetch_attempt.is_(None),
                                       models.Feed.next_fetch_attempt <= models.utc()))

            # XXX after queuing (and removed from Feed table)???
            all_ready = ready.count() # XXX report as gauge
            self.stats.gauge('ready_feeds', all_ready)

            rows = ready.order_by(models.Feed.next_fetch_attempt.asc().nulls_first(),
                                  models.Feed.id.desc())\
                        .limit(limit)\
                        .all()  # all rows
            feed_ids = [row[0] for row in rows]


        # mark as queued first to avoid race with workers
        now = dt.datetime.utcnow()
        with Session.begin() as session:  # this automatically commits and closes
            # mark each row in feed_ids as queued, and mark start time
            session.query(models.Feed)\
                   .filter(models.Feed.id.in_(feed_ids))\
                   .update({'last_fetch_attempt': now, 'queued': True},
                           synchronize_session=False)

            # create a fetch_event row for each feed:
            for feed_id in feed_ids:
                session.add(models.FetchEvent.from_info(feed_id, models.FetchEvent.EVENT_QUEUED))

        return self.queue_feeds(feed_ids)


    def queue_feeds(self, feed_ids: List[int]) -> int:
        queued = queue.queue_feeds(self.wq, feed_ids)

        # XXX compare queued w/ len(feed_ids) and complain if not equal??
        # XXX report unqueued as separate (labled) counter?

        self.stats.incr('queued_feeds', queued)

        total = len(feed_ids)
        # XXX complain if queued != total???
        self.logger.info(f"  queued {queued}/{total} feeds")

        return queued


def loop(queuer):
    """
    Loop monitoring & reporting queue length to stats server
    """
    old_qlen = old_time = None
    while True:
        # NOTE!! rate calculation will hickup if clock changed
        # (use time.monotonic() for rate calculation???)
        # but want wakeups at top of UTC minute

        t0 = time.time()
        queuer.logger.info(f"top {t0}") # XXX => debug

        qlen = queue.queue_length(queuer.wq) # queuer method??

        rate = 1000 / 60        # estimate: 1K/minute
        if old_qlen is not None and old_time is not None:
            # XXX calculate total processed over time running?
            delta_qlen = old_qlen - qlen
            delta_t = t0 - old_time

            if delta_t > 0:
                rate = delta_qlen / delta_t

        goal = round(rate * 4)  # minutes to keep queued
        queuer.logger.info(f"qlen {qlen} goal {goal}")
        if qlen < goal/2:
            queuer.find_and_queue_feeds(goal-qlen) # top off queue
            qlen = queue.queue_length(queuer.wq) # after find_and_queue_feeds

        tnext = (t0 - t0%60) + 60  # top of minute after wake time
        old_time = t1 = time.time()
        old_qlen = qlen

        s = tnext - t1             # time until then to sleep
        if s > 0:
            queuer.logger.info(f"t1 {t1} tnext {tnext} sleep {s}") # XXX => debug
            time.sleep(s)

if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    logger.info("Starting Feed Queueing")

    stats = Stats.init('queue_feeds')

    redis = queue.redis_connection()
    wq = queue.workq(redis)

    queuer = Queuer(stats, wq, logger)

    # PLB TEMP: try to show SQL (put on an option?)
    #logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

    # support passing in one or more feed ids on the command line
    if len(sys.argv) > 1:
        if sys.argv[1] == '--loop':
            sys.exit(loop(queuer))

        feed_ids = [int(id) for id in sys.argv[1:]]
        # XXX look up Feed entries by id?
        # just exists(.....filter(models.Feed.id.in_(feed_ids))) ???
        queuer.queue_feeds(feed_ids)
    else:
        queuer.find_and_queue_feeds(MAX_FEEDS)
