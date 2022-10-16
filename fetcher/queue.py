"""
worker queue support
(now using much simpler RQ)
tries to wrap all aspects of work queuing system in use.

Should probably implement a (singleton?) class with methods that wraps the
queuing system in use (once ops list is settled)
"""

import datetime
import logging
from typing import List, Optional

from redis.client import StrictRedis
from rq import Connection, Queue, SimpleWorker
from rq.local import LocalStack
from sqlalchemy import text
from sqlalchemy.engine.url import make_url

from fetcher.config import conf
from fetcher.database import Session
from fetcher.database.models import Feed
import fetcher.tasks            # for feed_worker

WORKQ_NAME = 'workq'            # make configurable?

logger = logging.getLogger(__name__)


def get_session():
    """
    Get SQLAlchemy connection for current worker process
    """
    return Session()

################
# to allow config fetch, connect after includes complete
# XXX wrap in a singleton??


def redis_connection():
    u = make_url(conf.REDIS_URL)     # SQLAlchemy URL object
    if not u:
        raise Exception(f"Bad REDIS_URL {conf.REDIS_URL}")
    # XXX assert u.drivername == 'redis'?
    return StrictRedis(host=u.host, port=u.port or 6379,
                       password=u.password, username=u.username)

################


def workq(rconn: Optional[StrictRedis] = None) -> Queue:
    """
    Return RQ Queue for enqueuing work, clearing queue.
    """
    if not rconn:
        rconn = redis_connection()
    # takes serializer=JSONSerializer
    return Queue(WORKQ_NAME, connection=rconn)

################


def queue_feeds(wq: Queue, feed_ids: List[int], ts_iso: str) -> int:
    """
    Queue feed_ids to work queue
    ts_iso expected to be return from datetime.datetime.isoformat()
    """
    try:
        job_datas = [
            Queue.prepare_data(
                func=fetcher.tasks.feed_worker,
                args=(id, ts_iso),
                result_ttl=0,  # don't care about result
                failure_ttl=0,  # don't care about failures
                # timeout?
                # retry?
            ) for id in feed_ids
        ]
        jobs = wq.enqueue_many(job_datas)
        queued = len(jobs)
    except BaseException:
        # XXX complain?
        queued = 0
    return queued

################


def worker():
    """
    run as worker, called by scripts/worker.py
    """
    with Connection(redis_connection()) as conn:
        w = SimpleWorker([WORKQ_NAME], connection=conn)

        # "The return value indicates whether any jobs were processed."
        w.work()

################
# called from scripts/queue_feeds.py


def queue_length(q: Queue) -> int:
    return q.count


def queue_active(q: Queue) -> int:
    """
    rq "started" jobs not included in queue_length
    """
    return q.started_job_registry.count


def queue_workers(q: Queue) -> int:
    """return number of workers for queue"""
    return len(SimpleWorker.all(queue=q))

################


def clear_queue():
    with Session() as session:
        logger.info("Getting feeds table lock.")
        # for duration of transaction:
        session.execute(text("LOCK TABLE feeds"))
        logger.info("Locked.")

        logger.info("Purging work queue.")
        # Only this bit is queuing system specific:
        with redis_connection() as r:
            q = workq(r)
            q.empty()

        logger.info("Clearing Feed.queued column.")
        session.query(Feed).filter(Feed.queued == True)\
                           .update({'queued': False})

        logger.info("Committing.")
        session.commit()  # releases lock
