import logging
import datetime as dt
import sys

# PyPI
from sqlalchemy import text, or_

# app
from fetcher import MAX_FEEDS
import fetcher.tasks as tasks
from fetcher.database import engine, Session
import fetcher.database.models as models
from fetcher.stats import Stats


if __name__ == '__main__':

    logger = logging.getLogger(__name__)
    logger.info("Starting Feed Queueing")
    now = dt.datetime.now()

    stats = Stats('queue_feeds')

    # PLB TEMP: try to show SQL (put on an option?)
    #logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

    # support passing in one or more feed ids on the command line
    args = sys.argv[1:]         # PLB want just positional args
    if args:
        feed_ids = [int(id) for id in args]
    else:
        # no ids on command line, so default to regular automated behaviour:
        # Find some active, unqueued feeds that have not been checked,
        # or are past due for a check (oldest first).
        with Session.begin() as session:  # this automatically commits and closes
            rows = session.query(models.Feed)\
                          .filter(models.Feed.active.is_(True),
                                  models.Feed.system_enabled.is_(True),
                                  models.Feed.queued.is_(False),
                                  or_(models.Feed.next_fetch_attempt.is_(None),
                                      models.Feed.next_fetch_attempt <= models.utc()))\
                          .order_by(models.Feed.next_fetch_attempt.asc().nulls_first(),
                                    models.Feed.id.desc())\
                          .limit(MAX_FEEDS)\
                          .all()
            feed_ids = [row.id for row in rows]

    # mark as queued first to avoid race with workers
    with Session.begin() as session:  # this automatically commits and closes
        session.query(models.Feed)\
               .filter(models.Feed.id.in_(feed_ids))\
               .update({'last_fetch_attempt': now, 'queued': True}, # PLB just set queued??
                       synchronize_session=False)
        for feed_id in feed_ids:
            session.add(models.FetchEvent.from_info(feed_id, models.FetchEvent.EVENT_QUEUED))

    # queue work:
    for id in feed_ids:
        tasks.feed_worker.delay(id)
        # called a lotta times, but above call likely more expensive:
        stats.incr('queued_feeds')

    logger.info("  queued {} feeds".format(len(feed_ids)))
