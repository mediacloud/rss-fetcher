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

import requests

from fetcher.config import conf
from fetcher.database import Session
import fetcher.database.models as models
import fetcher.database.property as prop
from fetcher.logargparse import LogArgumentParser
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
        sleep_seconds: int,
        max_batches: int) -> int:

    token = conf.MCWEB_TOKEN    # get mcweb API token from environment
    if not token:
        logger.error("MCWEB_TOKEN not configured")
        return 255

    last_update = prop.UpdateFeeds.modified_since.get()
    luz = last_update or "0"
    lui = int(luz)
    if lui > 0:
        after = time.strftime("%F %T", time.gmtime(lui))
        logger.info("Fetching updates after {after}")

    url = f"{conf.MCWEB_URL}/api/sources/feeds/?modified_since={luz}&limit={batch_limit}"

    totals: StatsDict = {}
    batches: StatsDict = {}
    stats = Stats.get()         # get singleton

    def batch_stat(stat: str) -> None:
        """
        call once per batch
        """
        batches[stat] = batches.get(stat, 0) + 1
        stats.incr('update.batches', labels=[('status', stat)])

    rs = requests.Session()
    rs.headers.update({"Authorization": f"Token {token}"})

    batch_number = 1
    last_modified_at = None

    while True:
        logger.info(f"Fetching {url}")
        try:
            resp = rs.get(url,
                          timeout=mcweb_timeout,
                          verify=verify_certificates)
        except Exception as e:
            batch_stat("get_failed")
            logger.exception(url)
            return 1

        if resp.status_code != 200:
            logger.error(
                f"{url}: HTTP Status {resp.status_code} {resp.reason}")
            batch_stat("http_err")
            return 2

        try:
            data = json.loads(resp.text)
            items = data['results']
            nxt = data['next']
            rcount = data['count']
        except Exception as e:
            logger.exception(url)
            batch_stat("format")
            return 3

        logger.debug(
            f" OK text: {len(resp.text)} bytes, items: {len(items)}, total: {rcount}")

        now = dt.datetime.utcnow()

        batch_stats: StatsDict = {}

        def inc(stat: str) -> None:
            batch_stats[stat] = batch_stats.get(stat, 0) + 1
            totals[stat] = totals.get(stat, 0) + 1
            stats.incr('update.feeds', labels=[('status', stat)])

        need_commit = False
        with Session.begin() as session:  # type: ignore[attr-defined]
            for item in items:
                try:
                    iid = int(item['id'])
                    modified_at = item['modified_at']  # in ISO format, w/ 'Z'
                except (ValueError, KeyError) as e:
                    inc('bad_id')
                    continue

                f = session.get(models.Feed, iid)  # XXX lock for update??
                if f is None:
                    f = models.Feed()
                    f.id = iid
                    sec = random() * random_interval_mins * 60
                    f.next_fetch_attempt = now + dt.timedelta(seconds=sec)
                    logger.info(f"CREATE {iid} {modified_at}")
                    create = True
                else:
                    logger.info(f"UPDATE {iid} {modified_at}")
                    create = False

                # NOTE! This depends on the mcweb API returning items
                # ordered by modified_at time!!
                if not last_modified_at or modified_at > last_modified_at:
                    last_modified_at = modified_at

                # MAYBE only log messages when verbosity > 1?
                def check(dest: str,
                          src: str,
                          cast: Callable[[Any], Any] = identity,
                          allow_change: bool = True) -> int:
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

                    # may have been updated by fetcher from feed:
                    changes += check('name', 'name',
                                     allow_change=False)

                    changes += check('url', 'url')

                    # note names differ
                    changes += check('sources_id', 'source', int)
                    changes += check('active', 'admin_rss_enabled', bool)

                    changes += check('created_at', 'created_at', parse_timestamp,
                                     allow_change=False)

                    # ignoring modified_at, but if saved could be used for
                    # MAX(mcweb_modified_at) to know most recent update
                    # processed.

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
            log_stats(batch_stats, f"batch {batch_number}:", False)
            batch_number += 1
        # end with session
        url = nxt
        if not url:
            break
        if max_batches > 1:
            max_batches -= 1
        elif max_batches == 1:
            logger.info("reached batch limit")
            break
        batch_stat("ok")

        if nxt:
            time.sleep(sleep_seconds)
        else:
            logger.info("no more batches")
    # end while

    if last_modified_at:
        # Using modified_at timestamp from remote database means we
        # don't need to worry about clock skews if we're running on a
        # different server than they are, *BUT* mcweb only wants time
        # truncated to whole seconds, AND only returns entries AFTER
        # that second!!!
        t = parse_timestamp(last_modified_at)

        tt = t.timestamp()
        new_modified_since = str(int(tt))
        logger.info(f"Updating modified_since to {new_modified_since}")
        prop.UpdateFeeds.modified_since.set(new_modified_since)

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

    # option to delete all feeds (and reset last-modified)???
    p.add_argument('--reset-last-modified', action='store_true',
                   help="reset saved last-modified time first")

    SLEEP = 5
    p.add_argument('--sleep-seconds', default=SLEEP, type=int,
                   help=f"time to sleep between batch requests in seconds (default: {SLEEP})")

    # all of these _COULD_ be command line options....
    random_interval_mins: int = conf.DEFAULT_INTERVAL_MINS
    mcweb_timeout: int = conf.MCWEB_TIMEOUT
    verify_certificates: bool = conf.VERIFY_CERTIFICATES

    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    if args.reset_last_modified:
        prop.UpdateFeeds.modified_since.unset()

    sys.exit(run(random_interval_mins=random_interval_mins,
                 mcweb_timeout=mcweb_timeout,
                 verify_certificates=verify_certificates,
                 batch_limit=args.batch_limit,
                 sleep_seconds=args.sleep_seconds,
                 max_batches=args.max_batches))
