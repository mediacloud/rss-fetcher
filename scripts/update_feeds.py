"""
Update Feeds table using mcweb API
"""

import csv
import datetime as dt
import json
import logging
import sys
import time
from collections import Counter
from random import random       # low-fi random ok
from typing import Any, Callable, Dict, TypeAlias

# PyPI
from mediacloud.api import DirectoryApi  # type: ignore[import-untyped]
from sqlalchemy.sql.expression import delete, select

# local
import fetcher.database.property as prop
from fetcher.config import conf
from fetcher.database import Session
from fetcher.database.models import Feed, FetchEvent
from fetcher.stats import Stats


def parse_timestamp(s: str) -> dt.datetime:
    """
    parse JSON datetime string from mcweb
    """
    return dt.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S.%fZ')


StatsCount: TypeAlias = Counter[str]


def log_stats(stats: StatsCount, title: str, always: bool = True) -> None:
    if stats:
        values = ', '.join([f"{key}: {value}" for key, value in stats.items()])
    else:
        if not always:
            return
        values = '(none)'
    logger.info(f"{title} {values}")


def identity(x: Any) -> Any:
    """identity cast for db fields"""
    return x


# all arguments must be passed, and by keyword
def run(*,
        mcweb_token: str,
        sleep_seconds: float,
        full_sync: bool,
        dry_run: bool) -> int:

    limit = 1000
    totals: StatsCount = Counter()
    batches: StatsCount = Counter()
    stats = Stats.get()         # get singleton

    def batch_stat(stat: str) -> None:
        """
        call once per batch
        """
        batches[stat] += 1
        stats.incr('update.batches', labels=[('status', stat)])

    dirapi = DirectoryApi(mcweb_token)

    vers = dirapi.version()
    server_now = vers.get('now')
    if server_now is None:
        batch_stat("vers_err")  # not a batch error
        return 1

    if full_sync:
        modified_since = 0.0
    else:
        modified_since = float(prop.UpdateFeeds.modified_since.get() or '0')
    logger.info(f"Fetching updates after {modified_since} before {server_now}")

    offset = 0
    mcweb_feeds_seen = set()    # for full_sync deletions
    while True:
        try:
            data = dirapi.feed_list(modified_since=modified_since,
                                    modified_before=server_now,
                                    limit=limit, offset=offset)
        except Exception as e:
            batch_stat("get_failed")
            logger.exception("dirapi.feed_list")
            return 2

        try:
            items = data['results']
            rcount = data['count']
        except Exception as e:
            logger.exception("bad response")
            batch_stat("format")
            return 4

        logger.debug(
            f" OK text: items: {len(items)}, total: {rcount}")

        def inc(stat: str, n: int = 1) -> None:
            totals[stat] += n
            stats.incr('update.feeds', labels=[('status', stat)])

        need_commit = False
        dtnow = dt.datetime.utcnow()

        if not items:
            break

        with Session() as session:
            for item in items:
                offset += 1
                try:
                    iid = int(item['id'])
                except (ValueError, KeyError) as e:
                    inc('bad_id')
                    continue

                mcweb_feeds_seen.add(iid)
                f = session.get(Feed, iid)  # XXX lock for update??
                if f is None:
                    f = Feed()
                    f.id = iid
                    logger.info(f"CREATE {iid}")
                    create = True
                else:
                    logger.info(f"UPDATE {iid}")
                    create = False

                # MAYBE only log messages when verbosity > 1?
                def check(dest: str,
                          src: str,
                          cast: Callable[[Any], Any] = identity,
                          allow_change: bool = True,
                          optional: bool = False) -> int:
                    """
                    returns 1 if field changed, else 0
                    """
                    if src not in item:
                        if optional:
                            logger.debug(
                                " check: %s/%s optional and missing", src, dest)
                        else:
                            logger.warning(" check: %s/%s missing", src, dest)
                            return 0

                    curr = getattr(f, dest)
                    raw = item[src]
                    try:
                        new = cast(raw)
                    except RuntimeError as e:  # _should_ be a ValueError
                        logger.error("  check: error for %s/%s value %s: %r",
                                     src, dest, raw, e)
                        return 0

                    if new == curr:
                        logger.debug(" check: %r == %r", new, curr)
                        return 0  # no change

                    # test if already set, and do not change:
                    if curr:
                        if not allow_change:
                            logger.info(
                                f"  ignoring {dest} from {curr} to {new}")
                            return 0  # no change
                        logger.info(f"  updating {dest} from {curr} to {new}")
                    else:       # no current value
                        logger.info(f"  setting {dest} to {new}")
                    setattr(f, dest, new)
                    return 1    # changed

                try:
                    changes = 0

                    changes += check('url', 'url')

                    # take name from mcweb: we write only to rss-title column
                    changes += check('name', 'name')

                    # note names differ
                    changes += check('sources_id', 'source', int)
                    changes += check('active', 'admin_rss_enabled', bool)

                    # should NOT be optional (does not auto-populate)
                    changes += check('created_at', 'created_at',
                                     parse_timestamp,
                                     allow_change=False)  # only accept on create

                    if dry_run: # before any counters incremented
                        session.expunge(f)
                        continue

                    if changes == 0:
                        logger.info(" no change")
                        inc('no_change')
                        session.expunge(f)
                        continue

                    if create:
                        inc('create')
                        session.add(f)
                    else:
                        inc('update')
                    need_commit = True
                except Exception:
                    logger.exception('bad')
                    inc('bad')
                    continue

            if need_commit:
                session.commit()
        # end with session
        batch_stat("ok")
        logger.info(f"sleeping {sleep_seconds} sec")
        time.sleep(sleep_seconds)

    if not dry_run:
        new = str(server_now)
        logger.info(f"setting new modified_since: {new}")
        prop.UpdateFeeds.modified_since.set(new)
        prop.UpdateFeeds.next_url.unset()  # no longer used

    if full_sync:
        with Session() as session:
            local_feeds = set(
                row[0] for row in
                session.execute(select(Feed.id))
            )

            nlocal = len(local_feeds)
            mcweb_feed_count = len(mcweb_feeds_seen)
            logger.info("mcweb %d feeds, local %d feeds", mcweb_feed_count, nlocal)
            if nlocal > mcweb_feed_count:
                not_seen = local_feeds - mcweb_feeds_seen
                logger.info("feeds to delete: %s", ", ".join(str(f) for f in sorted(not_seen)))

                if not dry_run:
                    res = session.execute(delete(Feed).where(Feed.id.in_(not_seen)))
                    inc('deleted', res.rowcount)

                    res = session.execute(delete(FetchEvent).where(FetchEvent.feed_id.in_(not_seen)))
                    logger.info("deleted %d fetch events", res.rowcount)

                    # leaving Stories in place, in case an active feed fetches dups

                    session.commit()

    log_stats(batches, "BATCHES")
    log_stats(totals, "FEEDS")
    return 0


if __name__ == '__main__':
    from fetcher.logargparse import LogArgumentParser
    from fetcher.pidfile import LockedException, PidFile

    SCRIPT = 'update_feeds'

    logger = logging.getLogger(SCRIPT)
    p = LogArgumentParser(SCRIPT, 'update feeds using mcweb API')

    p.add_argument('--reset-last-modified', action='store_true',
                   help="reset saved last-modified time first")

    p.add_argument('--full-sync', action='store_true',
                   help="pull ALL feeds, remove any extras")

    p.add_argument('--dry-run', action='store_true',
                   help="don't update database")

    SLEEP = 0.5
    p.add_argument('--sleep-seconds', default=SLEEP, type=float,
                   help=f"time to sleep between batch requests in seconds (default: {SLEEP})")

    mcweb_token: str = conf.MCWEB_TOKEN

    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    if args.reset_last_modified:
        prop.UpdateFeeds.modified_since.unset()

    prop.UpdateFeeds.next_url.unset()  # no longer used

    try:
        with PidFile(SCRIPT):
            sys.exit(
                run(mcweb_token=mcweb_token,
                    sleep_seconds=args.sleep_seconds,
                    full_sync=args.full_sync,
                    dry_run=args.dry_run))
    except LockedException:
        logger.error("could not get lock")
        exit(255)
