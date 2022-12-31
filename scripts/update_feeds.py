"""
Read CSV dumped from mcweb-db sources_feed table to update our feeds table.
(run by dokku-scripts/sync-feeds.sh from /etc/cron.d/rss-fetcher)
"""

import csv
import datetime as dt
import json
import logging
from random import random       # low-fi random ok
import sys
import time
from typing import Any, Callable, Dict

from fetcher.config import conf
from fetcher.database import Session
import fetcher.database.models as models
import fetcher.database.property as prop
from fetcher.logargparse import LogArgumentParser
from fetcher.mcweb_api import MCWebAPI, MODIFIED_BEFORE
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
        values = '(nothing)'
    logger.info(f"{title} {values}")


def identity(x: Any) -> Any:
    return x


# all arguments must be passed, and by keyword
def run(*,
        random_interval_mins: int,
        mcweb_timeout: int,
        verify_certificates: bool,
        batch_limit: int,
        sleep_seconds: float,
        max_batches: int) -> int:

    totals: StatsDict = {}
    batches: StatsDict = {}
    stats = Stats.get()         # get singleton

    def batch_stat(stat: str) -> None:
        """
        call once per batch
        """
        batches[stat] = batches.get(stat, 0) + 1
        stats.incr('update.batches', labels=[('status', stat)])

    mcweb = MCWebAPI(timeout=mcweb_timeout)

    if batch_limit:             # doing short sprints?
        # try resuming from saved URL, if any
        url = prop.UpdateFeeds.next_url.get()
        if url:
            logger.info(f"batch_limit set, next_url: {url}")
            if '?' in url:
                _, query = url.split('?', 1)
                for param in query.split('&'):
                    if param.startswith(MODIFIED_BEFORE):
                        if '=' in param:
                            _, nstr = param.split('=', 1)
                            now = float(nstr)
                        else:
                            logger.warning(f"no '=' in {param}")
                            url = None
                        break
                else:           # for param...
                    logger.warning(f"{MODIFIED_BEFORE} not in {url}")
            else:
                logger.warning(f"no query in {url}")
                url = None

    if not url:
        vers = mcweb.version()
        web_now = vers.get('now')
        if web_now is None:
            batch_stat("vers_err")  # not a batch error
            return 1

        last_update = float(prop.UpdateFeeds.modified_since.get() or '0')
        logger.info(f"Fetching updates after {last_update} before {web_now}")
        url = mcweb.feeds_url(last_update, web_now, batch_limit)

    while url:
        logger.info(f"Fetching {url}")
        try:
            data = mcweb.get_url_dict(url)  # XXX timeout?
        except Exception as e:
            batch_stat("get_failed")
            logger.exception(url)
            return 2

        try:
            items = data['results']
            nxt = data['next']
            rcount = data['count']
        except Exception as e:
            logger.exception(url)
            batch_stat("format")
            return 4

        logger.debug(
            f" OK text: items: {len(items)}, total: {rcount}")

        def inc(stat: str) -> None:
            totals[stat] = totals.get(stat, 0) + 1
            stats.incr('update.feeds', labels=[('status', stat)])

        need_commit = False
        dtnow = dt.datetime.utcnow()

        with Session() as session:
            for item in items:
                try:
                    iid = int(item['id'])
                except (ValueError, KeyError) as e:
                    inc('bad_id')
                    continue

                f = session.get(models.Feed, iid)  # XXX lock for update??
                if f is None:
                    f = models.Feed()
                    f.id = iid
                    sec = random() * random_interval_mins * 60
                    f.next_fetch_attempt = dtnow + dt.timedelta(seconds=sec)
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
                          optional: bool = True) -> int:
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
                    if new != curr:
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

                    # we write to rss-title column
                    changes += check('name', 'name')
                    changes += check('url', 'url')

                    # note names differ
                    changes += check('sources_id', 'source', int)
                    changes += check('active', 'admin_rss_enabled', bool)

                    # required (does not auto-populate):
                    changes += check('created_at', 'created_at', parse_timestamp,
                                     allow_change=False)

                    if changes == 0:
                        logger.info(" no change")
                        inc('no_change')
                        continue
                    session.add(f)
                    if create:
                        inc('created')
                    else:
                        inc('modified')
                    need_commit = True
                except Exception:
                    logger.exception('bad')
                    inc('bad')
                    continue

            if need_commit:
                session.commit()
        # end with session
        url = nxt
        if items:
            batch_stat("ok")

        if max_batches:
            # before url check (clear property if value is None)
            prop.UpdateFeeds.next_url.set(url)

        if url:
            if max_batches > 1:
                max_batches -= 1
            elif max_batches == 1:
                logger.info("reached batch limit")
                break

            time.sleep(sleep_seconds)
    else:                       # while url
        new = str(web_now)
        logger.info(f"setting new modified_since: {new}")
        prop.UpdateFeeds.modified_since.set(new)
        prop.UpdateFeeds.next_url.unset()

    log_stats(batches, "BATCHES")
    log_stats(totals, "FEEDS")
    return 0


if __name__ == '__main__':
    SCRIPT = 'update_feeds'

    logger = logging.getLogger(SCRIPT)
    p = LogArgumentParser(SCRIPT, 'update feeds using mcweb API')

    BATCH = 500
    p.add_argument('--batch-limit', default=BATCH, type=int,
                   help=f"feed batch size to request (default: {BATCH})")

    MAX_BATCHES = 0
    p.add_argument('--max-batches', default=MAX_BATCHES, type=int,
                   help=f"number of batches to fetch (default: {MAX_BATCHES});"
                   " zero means no limit")

    p.add_argument('--reset-last-modified', action='store_true',
                   help="reset saved last-modified time first")

    SLEEP = 5
    p.add_argument('--sleep-seconds', default=SLEEP, type=float,
                   help=f"time to sleep between batch requests in seconds (default: {SLEEP})")

    # all of these _COULD_ be command line options....
    random_interval_mins: int = conf.DEFAULT_INTERVAL_MINS
    mcweb_timeout: int = conf.MCWEB_TIMEOUT
    verify_certificates: bool = conf.VERIFY_CERTIFICATES

    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    if args.reset_last_modified:
        prop.UpdateFeeds.modified_since.unset()

    sys.exit(
        run(random_interval_mins=random_interval_mins,
            mcweb_timeout=mcweb_timeout,
            verify_certificates=verify_certificates,
            batch_limit=args.batch_limit,
            sleep_seconds=args.sleep_seconds,
            max_batches=args.max_batches))
