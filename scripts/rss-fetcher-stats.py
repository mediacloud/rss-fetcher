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
from fetcher.database.models import Feed, Story
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
    query = (
        select(Feed.system_status,
               func.count(Feed.id),
               func.count(Feed.sources_id.distinct()))
        .where(Feed.last_fetch_success >= start)
        .group_by("system_status")
    )

    # sum in case status name truncation creates dups
    feed_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    with Session() as session:
        results = session.execute(query)
        for row in results:
            name = status_to_name(row[0])
            feed_counts[name] += row[1]
            source_counts[name] += row[2]
            sys_status_names.add(name)

    # loop for ALL known status strings
    # (counters stick at last value unless explicitly zeroed)
    for name in sys_status_names:
        count = feed_counts[name]
        labels = [('hours', hours), ('status', name)]
        gauge = 'feeds.recent'
        logger.debug('%s %r %d', gauge, labels, count)
        stats.gauge(gauge, count, labels=labels)

        count = source_counts[name]
        labels = [('hours', hours), ('status', name)]
        gauge = 'sources.recent'
        logger.debug('%s %r %d', gauge, labels, count)
        stats.gauge(gauge, count, labels=labels)


def report_top_domain_stories(stats: Stats, days: int = 3) -> None:
    start = dt.datetime.utcnow() - dt.timedelta(days=days)
    domain = Story.domain
    count = func.count(domain)
    query = (
        select(domain, count)
        .where(Story.fetched_at >= start)
        .group_by(domain)
        .order_by(count.desc())
        .limit(1)
    )

    with Session() as session:
        results = session.execute(query)
        for row in results:
            top_domain = row.domain
            top_count = row.count
            assert isinstance(top_count, int)

            logger.info("top domain for last %d days %s (%d stories)",
                        days, top_domain, top_count)

            if top_count == 0 or not top_domain:
                return

            labels = [('days', days)]

            # NOT reporting domain name: would end up keeping a time
            # series file per domain seen (high cardinality).  Could
            # report ALL counts as a timer, but that would mean
            # sending many thousands of stats packets each time.
            def g(name: str, value: int) -> None:
                gauge = f'stories.{name}'
                logger.debug('%s %r %s', gauge, labels, value)
                stats.gauge(gauge, value, labels=labels)

            g("top-domain.sum", top_count)
            g("top-domain.avg", top_count // days)
            break               # at most one row


if __name__ == '__main__':
    # prep file
    p = LogArgumentParser(SCRIPT, 'report rss-fetcher stats')
    p.add_argument('--interval', type=int, default=5 * 60)
    args = p.my_parse_args()       # parse logging args, output start message
    stats = Stats.get()            # after my_parse_args

    get_sys_status_names()
    while True:
        report_feeds_active(stats, 24)       # feeds active in last 24 hours
        report_top_domain_stories(stats)     # top domain story count
        time.sleep(args.interval - time.time() % args.interval)
