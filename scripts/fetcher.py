# XXX add fetch_done method to worker to update scoreboard

"""
"direct drive" feed fetcher: runs fetches in subprocesses without
queuing so that the exact number of concurrent requests for a given
source can be managed directly.
"""

import logging
import time
from typing import Any, List, Optional

# PyPI:
from sqlalchemy import update

# app
from fetcher.config import conf
from fetcher.database import Session
from fetcher.database.models import Feed, utc
from fetcher.direct import Manager, Worker
from fetcher.headhunter import HeadHunter, ready_feeds
from fetcher.logargparse import LogArgumentParser
#from fetcher.stats import Stats
from fetcher.tasks import feed_worker

SCRIPT = 'fetcher'
logger = logging.getLogger(SCRIPT)

if __name__ == '__main__':
    task_timeout = conf.TASK_TIMEOUT_SECONDS

    p = LogArgumentParser(SCRIPT, 'Feed Fetcher')
    # XXX add pid to log formatting????

    workers = conf.RSS_FETCH_WORKERS
    p.add_argument('--workers', default=workers, type=int,
                   help=f"number of worker processes (default: {workers})")

    # positional arguments:
    p.add_argument('feeds', metavar='FEED_ID', nargs='*', type=int,
                   help='Fetch specific feeds and exit.')

    args = p.my_parse_args()       # parse logging args, output start message

    hunter = HeadHunter()

    # here for access to hunter!
    class FetcherWorker(Worker):
        def fetch(self, item):  # called in Worker to do work
            """
            passed entire item (as dict) for use by fetch_done
            """
            return feed_worker(item['id'])

        def fetch_done(self, ret):  # callback in Manager
            # print("fetch_done", ret)
            item = ret['args'][0]  # recover "fetch" first arg (dict)
            hunter.completed(item)

    manager = Manager(args.workers, FetcherWorker)

    if args.feeds:
        # force feed with feed ids from command line
        hunter.refill(args.feeds)
    else:
        # clear all Feed.queued columns
        with Session() as session:
            session.execute(update(Feed)
                            .values(queued=False)
                            .where(Feed.queued.is_(True)))
            hunter.get_ready(session) # prime total_ready
            session.commit()

    next_wakeup = 0
    while hunter.have_work():
        # here initially, or after manager.poll()
        # (will starve when tons of work available?!)
        t0 = time.time()
        if t0 > next_wakeup:
            with Session() as session:
                # XXX report as "ready" gauge:
                logger.info(f"ready: {ready_feeds(session)} {hunter.total_ready}")

        while w := manager.find_available_worker():
            item = hunter.find_work()
            if item is None:
                # XXX counter?
                break

            # NOTE! returned item has been already been marked as "issued"
            feed_id = item['id']
            with Session() as session:
                session.execute(
                    update(Feed)
                    .where(Feed.id == feed_id)
                    .values(queued=True)) # now means active!!
                session.commit()

            # pass entire item as dict for use by fetch_done callback
            w.call('fetch', dict(item))

        # XXX report as "active" gauge
        logger.info(f"active: {manager.active_workers}/{manager.nworkers} {hunter.total_ready}")

        next_wakeup = t0 - (t0 % 60) + 60
        # XXX use hunter.next_db_check instead of next_wakeup if smaller??

        # sleep until next_wakeup, or a worker finishes a feed
        stime = next_wakeup - time.time()
        manager.poll(stime)

    # here when feeds given command line
    while manager.active_workers > 0:
        manager.poll()

