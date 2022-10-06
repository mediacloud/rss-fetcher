"""
worker queue support
(now using much simpler RQ)
tries to wrap all aspects of work queuing system in use.

Should probably implement a (singleton?) class with methods that wraps the
queuing system in use (once ops list is settled)
"""

from typing import List

from redis.client import StrictRedis
from rq import Connection, Queue, SimpleWorker
from rq.local import LocalStack
from sqlalchemy.engine.url import make_url

from fetcher import REDIS_URL
from fetcher.database import Session
import fetcher.tasks

WORKQ_NAME = 'workq'            # XXX make config?

# only ever contains one item
# needed?? RQ Worker not multi-threaded
#   with SimpleWorker all in one process??
_sessions = LocalStack()

def get_session():
    """
    Get SQLAlchemy connection
    """
    s = _sessions.top
    if not s:
        s = Session()
        _sessions.push(s)
    return s

################
# to allow config fetch, connect after includes complete
# XXX wrap in a singleton??

def redis_connection():
    u = make_url(REDIS_URL)     # SQLAlchemy URL object
    if not u:
        raise Exception(f"Bad REDIS_URL {REDIS_URL}")
    # XXX assert u.drivername == 'redis'?
    return StrictRedis(host=u.host, port=u.port or 6379,
                       password=u.password, username=u.username)

################

# XXX wrap in a singleton?
def workq(rconn):
    """
    Return RQ Queue for enqueuing work, clearing queue.
    """
    if not rconn:
        rconn = redis_connection()
    # takes serializer=JSONSerializer
    return Queue(WORKQ_NAME, connection=rconn)

################

def queue_feeds(wq, feed_ids: List[int]):
    """
    Queue feed_ids to work queue
    """
    try:
        job_datas = [
            Queue.prepare_data(
                func=fetcher.tasks.feed_worker,
                args=(id,), # also pass datetime used to set last_fetch_attempt??
                result_ttl=0, # don't care about result
                failure_ttl=0, # don't care about failures
                # timeout?
                # retry?
                ) for id in feed_ids
        ]
        jobs = wq.enqueue_many(job_datas)
        queued = len(jobs)
    except:
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
# called from scripts/clear_queue.py

def clear_work_queue():
    with redis_connection() as r:
        q = workq(r)
        q.empty()

################
# called from scripts/queue_feeds.py

def queue_length(q):
    return q.count

REGISTRIES = ('deferred', 'scheduled', 'canceled', 'started', 'finished', 'failed')
def reg_counts(q):
    return {rname: getattr(q, rname + '_job_registry').count for rname in REGISTRIES}
