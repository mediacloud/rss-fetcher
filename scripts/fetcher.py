# XXX use pidfile lock & clear next_fetch_attempt on command line feeds???
"""
"direct drive" feed fetcher: runs fetches in subprocesses using
fetcher.direct without queuing so that the exact number of concurrent
requests for a given source can be managed directly by
fetcher.headhunter.
"""

import logging
import time
from typing import Any, Dict, List, Optional

# PyPI:
from sqlalchemy import update

# app
from fetcher.config import conf
from fetcher.database import Session
from fetcher.database.models import Feed, utc
from fetcher.direct import Manager, Worker
from fetcher.headhunter import HeadHunter, Item, ready_feeds
from fetcher.logargparse import LogArgumentParser
from fetcher.stats import Stats
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

    # XXX take command line args for concurrency, fetches/sec

    # positional arguments:
    p.add_argument('feeds', metavar='FEED_ID', nargs='*', type=int,
                   help='Fetch specific feeds and exit.')

    args = p.my_parse_args()       # parse logging args, output start message

    hunter = HeadHunter()

    # here for access to hunter!
    class FetcherWorker(Worker):
        def fetch(self, item: Item) -> None:  # called in Worker to do work
            """
            passed entire item (as dict) for use by fetch_done
            """
            print("fetch", item, "***")
            feed_worker(item['id'])

        def fetch_done(self, ret: Dict) -> None:  # callback in Manager
            # print("fetch_done", ret)
            item = ret['args'][0]  # recover "fetch" first arg (dict)
            hunter.completed(item)

    # XXX pass command line args for concurrency, fetches/sec??
    manager = Manager(args.workers, FetcherWorker)

    if args.feeds:
        # force feed with feed ids from command line
        hunter.refill(args.feeds)
    else:
        # clear all Feed.queued columns
        with Session() as session:
            res = session.execute(
                update(Feed)
                .values(queued=False)
                .where(Feed.queued.is_(True)))
            # res.rowcount is number of effected rows?
            hunter.get_ready(session)  # prime total_ready
            session.commit()

    next_wakeup = 0.0
    while hunter.have_work():
        # here initially, or after manager.poll()
        # (will starve when tons of work available?!)
        t0 = time.time()
        if t0 > next_wakeup:
            with Session() as session:
                # XXX report as "ready" gauge(s):
                hunter.get_ready(session) # prime total_ready
                logger.info(
                    f"ready: {ready_feeds(session)} {hunter.total_ready}")

        while w := manager.find_available_worker():
            item = hunter.find_work()
            if item is None:    # no issuable work available
                # XXX counter?
                break

            # NOTE! returned item has been already been marked as
            # "issued" by headhunter

            feed_id = item['id']
            with Session() as session:
                # "queued" now means "currently being fetched"
                res = session.execute(
                    update(Feed)
                    .where(Feed.id == feed_id)
                    .values(queued=True, last_fetch_attempt=utc()))
                # res.rowcount is number of effected rows?
                session.commit()

            # pass entire item as dict for use by fetch_done callback
            w.call('fetch', item)

        # XXX report as "active" gauge
        logger.info(
            f"active: {manager.active_workers}/{manager.nworkers} ready: {hunter.on_hand()} {hunter.total_ready}")

        next_wakeup = t0 - (t0 % 60) + 60
        # XXX use hunter.next_db_check instead of next_wakeup if smaller??

        # sleep until next_wakeup, or a worker finishes a feed
        stime = next_wakeup - time.time()
        manager.poll(stime)

    # here when feeds given command line
    while manager.active_workers > 0:
        manager.poll()
