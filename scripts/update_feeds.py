"""
Update Feeds table using mcweb API
"""

import csv
import datetime as dt
import json
import logging
from mediacloud.api import DirectoryApi  # type: ignore[import]
from random import random       # low-fi random ok
import sys
import time
from typing import Any, Callable, Dict

from fetcher.config import conf
from fetcher.database import Session
import fetcher.database.models as models
import fetcher.database.property as prop
from fetcher.stats import Stats


def parse_timestamp(s: str) -> dt.datetime:
    """
    parse JSON datetime string from mcweb
    """
    return dt.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S.%fZ')


StatsDict = Dict[str, int]


def log_stats(stats: StatsDict, title: str, always: bool = True) -> None:
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
        sleep_seconds: float) -> int:

    limit = 1000
    totals: StatsDict = {}
    batches: StatsDict = {}
    stats = Stats.get()         # get singleton

    def batch_stat(stat: str) -> None:
        """
        call once per batch
        """
        batches[stat] = batches.get(stat, 0) + 1
        stats.incr('update.batches', labels=[('status', stat)])

    dirapi = DirectoryApi(mcweb_token)

    vers = dirapi.version()
    server_now = vers.get('now')
    if server_now is None:
        batch_stat("vers_err")  # not a batch error
        return 1

    modified_since = float(prop.UpdateFeeds.modified_since.get() or '0')
    logger.info(f"Fetching updates after {modified_since} before {server_now}")

    offset = 0
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

        def inc(stat: str) -> None:
            totals[stat] = totals.get(stat, 0) + 1
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

                f = session.get(models.Feed, iid)  # XXX lock for update??
                if f is None:
                    f = models.Feed()
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
                    if optional and src not in item:
                        return 0
                    curr = getattr(f, dest)
                    new = cast(item[src])

                    # test if already set, and do not change:
                    if curr and not allow_change:
                        # ignore "ignoring" message if no change!
                        if new != curr:
                            logger.info(
                                f"  ignoring {dest} from {curr} to {new}")
                        return 0

                        if curr:
                            logger.info(
                                f"  updating {dest} from {curr} to {new}")
                        else:
                            logger.info(f"  setting {dest} to {new}")
                        setattr(f, dest, new)
                        return 1
                    return 0

                try:
                    changes = 0

                    changes += check('url', 'url')

                    # take name from mcweb: we write only to rss-title column
                    changes += check('name', 'name')

                    # note names differ
                    changes += check('sources_id', 'source', int)
                    changes += check('active', 'admin_rss_enabled', bool)

                    # should NOT be optional (does not auto-populate),
                    # only accept first time
                    changes += check('created_at', 'created_at',
                                     parse_timestamp,
                                     allow_change=False)

                    if changes == 0:
                        logger.info(" no change")
                        inc('no_change')
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

    new = str(server_now)
    logger.info(f"setting new modified_since: {new}")
    prop.UpdateFeeds.modified_since.set(new)
    prop.UpdateFeeds.next_url.unset()  # no longer used

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
                    sleep_seconds=args.sleep_seconds))
    except LockedException:
        logger.error("could not get lock")
        exit(255)
