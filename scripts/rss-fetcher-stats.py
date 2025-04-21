"""
report (database) stats
created for dashboard
"""

import datetime as dt
import logging
import time
from collections import Counter

from sqlalchemy import func, select

from fetcher.database import Session
from fetcher.database.models import Feed
from fetcher.logargparse import LogArgumentParser
from fetcher.stats import Stats

SCRIPT = 'rss-fetcher-stats'

logger = logging.getLogger(SCRIPT)  # instead of __main__

sys_status_names = set()


def status_to_name(status: str) -> str:
    """
    take Feed.system_status string, return counter label
    """
    toks = status.lower().split()
    return '-'.join(toks[:2])


def get_sys_status_names() -> None:
    query = select(func.distinct(Feed.system_status))
    with Session() as session:
        results = session.execute(query)
        for row in results:
            name = status_to_name(row[0] or 'null')
            sys_status_names.add(name)


def report_feeds_active(stats: Stats, hours: int = 24) -> None:
    start = dt.datetime.utcnow() - dt.timedelta(hours=hours)
    query = (select(Feed.system_status, func.count(Feed.id))
             .where(Feed.last_fetch_success >= start)
             .group_by("system_status"))

    # sum in case status name truncation creates dups
    counts: Counter[str] = Counter()
    with Session() as session:
        results = session.execute(query)
        for row in results:
            name = status_to_name(row[0])
            counts[name] += row[1]
            sys_status_names.add(name)

    # must output all names (counters stick at last value)
    for name in sys_status_names:
        count = counts[name]
        labels = [('hours', hours), ('status', name)]
        gauge = 'feeds.recent'
        logger.debug('%s %r %d', gauge, labels, count)
        stats.gauge(gauge, count, labels=labels)


if __name__ == '__main__':
    # prep file
    p = LogArgumentParser(SCRIPT, 'report rss-fetcher stats')
    p.add_argument('--interval', type=int, default=5 * 60)
    args = p.my_parse_args()       # parse logging args, output start message
    stats = Stats.get()            # after my_parse_args

    get_sys_status_names()
    while True:
        report_feeds_active(stats, 24)       # feeds active in last 24 hours
        time.sleep(args.interval - time.time() % args.interval)
