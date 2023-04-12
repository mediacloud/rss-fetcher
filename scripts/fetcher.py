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
from fetcher.database import Session, SessionType
from fetcher.database.models import Feed, utc
from fetcher.direct import Manager, Worker
from fetcher.headhunter import HeadHunter
from fetcher.logargparse import LogArgumentParser
from fetcher.stats import Stats
from fetcher.tasks import feed_worker

SCRIPT = 'fetcher'
logger = logging.getLogger(SCRIPT)

if __name__ == '__main__':
    task_timeout = conf.TASK_TIMEOUT_SECONDS

    p = LogArgumentParser(SCRIPT, 'Feed Fetcher')

    WORKERS = 2 # XXX get from conf.RSS_FETCHER_WORKERS so rebuild not needed!!
    p.add_argument('--workers', default=WORKERS, type=int,
                   help=f"number of worker processes (default: {WORKERS})")

    # positional arguments:
    p.add_argument('feeds', metavar='FEED_ID', nargs='*', type=int,
                   help='Fetch specific feeds and exit.')

    args = p.my_parse_args()       # parse logging args, output start message

    hunter = HeadHunter()

    # here for access to hunter!
    class FetcherWorker(Worker):
        def fetch(self, item):
            """
            passed entire item (as dict) for use by fetch_done
            """
            return feed_worker(item['id'])

        def fetch_done(self, ret):  # callback
            print("fetch_done", ret)
            item = ret['args'][0]  # recover "fetch" first arg (dict)
            hunter.completed(item)

    manager = Manager(args.workers, FetcherWorker)

    if args.feeds:
        hunter.reset(args.feeds)
    else:
        # clear all Feed.queued columns
        with Session() as session:
            session.execute(update(Feed).values(queued=False).where(Feed.queued.is_(True)))
            session.commit()

    t0 = time.time()
    while hunter.have_work():
        while w := manager.find_available_worker():
            item = hunter.find_work()
            if item is None:
                break

            feed_id = item['id']
            print("here", item, feed_id)
            with Session() as session:
                session.execute(
                    update(Feed)
                    .where(Feed.id == feed_id)
                    .values(queued=True)) # now means active!!
                session.commit()
            # XXX call hunter.issue(item)?????

            # pass entire item as dict for use by fetch_done callback
            w.call('fetch', dict(item))

        # XXX report manager.active_workers as "active" gauge
        next_wakeup = t0 - (t0 % 60) + 60
        # XXX use hunter.next_db_check instead of next_wakeup if smaller??
        now = time.time()
        stime = next_wakeup - now
        logger.debug(f"poll: t0 {t0} now {now} nw {next_wakeup} sleep {stime}")

        manager.poll(stime)

        now = time.time()
        logger.debug(f"awake: now {now} nw {next_wakeup}")
        if now > next_wakeup:
            logger.debug("DING!")
        t0 = now

    # here when feeds given on command line
    while manager.active_workers > 0:
        manager.poll()

