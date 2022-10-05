"""
worker queue support
(now using much simpler RQ)
tries to wrap all aspects of work queuing system in use.

Should probably implement a class with methods that wraps the
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

def redis_connection():
    u = make_url(REDIS_URL)     # SQLAlchemy URL object
    # XXX assert u.drivername == 'redis'?
    return StrictRedis(host=u.host, port=u.port, password=u.password, user=u.user)

################

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
    # batch queuing???
    # q.enqueue_many([
    #    Queue.prepare_data(count_words_at_url, 'http://nvie.com', job_id='my_job_id'),
    #    Queue.prepare_data(count_words_at_url, 'http://nvie.com', job_id='my_other_id'),
    # ])
    queued = 0
    for id in feed_ids:
        try:
            # job_timeout?
            wq.enqueue(fetcher.tasks.feed_worker,
                       args=(id,),
                       failure_ttl=0, # don't care about failures?
                       result_ttl=0, # don't care about result
                       # ttl (lifetime in queue)
            )
            queued += 1
        except:
            pass
    return queued

################

def worker():
    """
    run as worker, called by scripts/worker.py
    XXX parse sys.argv for options (log level), like celery.main?
    """
    with Connection(redis_connection()) as conn:
        w = SimpleWorker([WORKQ_NAME], connection=conn)

        # "The return value indicates whether any jobs were processed.":
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
    return len(q)

################
# info:

# from rq.worker import Worker
# worker = Worker.find_by_key('rq:worker:name')
# worker.successful_job_count  # Number of jobs finished successfully
# worker.failed_job_count # Number of failed jobs processed by this worker
# worker.total_working_time  # Amount of time spent executing jobs (in seconds)

def workers(rconn):
    wq = workq(rconn)
    return Worker.all(queue=wq)

