"""
worker queue support
now using much simpler RQ
"""

from redis.client import Redis
from rq import Connection, Queue, SimpleWorker
from rq.local import LocalStack

from fetcher import REDIS_HOST
from fetcher.database import Session

WORKQ_NAME = 'workq'            # XXX make config?

# only ever contains one item
# needed?? Worker not multi-threaded
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

# to allow config fetch, connect after includes complete
def redis_connection():
    return Redis(REDIS_HOST)

################

def workq(rconn):
    """
    return Queue for enqueuing work, clearing queue
    """
    if not rconn:
        rconn = redis_connection()
    # takes serializer=JSONSerializer
    return Queue(WORKQ_NAME, connection=rconn)

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
    q = workq()
    q.empty()

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

