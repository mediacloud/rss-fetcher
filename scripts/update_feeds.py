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
from fetcher.logargparse import LogArgumentParser
from fetcher.stats import Stats


def ptime(s: str) -> dt.datetime:
    """
    parse JSON datetime string from mcweb
    """
    return dt.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S.%fZ')


StatsDict = Dict[str, int]


def log_stats(stats: StatsDict, title: str = '') -> None:
    if stats:
        values = ', '.join([f"{key}: {value}" for key, value in stats.items()])
    else:
        if not title:
            return
        values = '(nothing)'
    logger.info(f"{title} {values}")


def identity(x: Any) -> Any:
    return x


def run(
        random_interval_mins: int = conf.DEFAULT_INTERVAL_MINS,
        mcweb_timeout: int = conf.MCWEB_TIMEOUT,
        verify_certificates: bool = conf.VERIFY_CERTIFICATES) -> int:

    t0 = time.time()            # TEMP save as last_modified on completion
    token = conf.MCWEB_TOKEN
    if not token:
        logger.error("MCWEB_TOKEN not configured")
        return 255

    last_update = 0             # XXX
    limit = 1000                # XXX take as arg?
    sleep_time = 5              # XXX take as arg?

    url = f"{conf.MCWEB_URL}/api/sources/feeds/?modified_since={last_update}&limit={limit}"
    headers = {"Authorization": f"Token {token}"}

    totals: StatsDict = {}
    batches: StatsDict = {}
    stats = Stats.get()         # get singleton

    def batch_stat(stat: str) -> None:
        """
        call once per batch
        """
        batches[stat] = batches.get(stat, 0) + 1
        stats.incr('update.batches', labels=[('status', stat)])

    while url:
        logger.info(f"Fetching updates w/ {url}")
        try:
            resp = requests.get(url,
                                headers=headers,
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
            f"{url} OK text: {len(resp.text)} bytes, items: {len(items)}, total: {rcount}")

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
                except (ValueError, KeyError) as e:
                    inc('bad_id')
                    continue

                f = session.get(models.Feed, iid)  # XXX lock for update??
                if f is None:
                    f = models.Feed()
                    f.id = iid

                    # XXX smaller interval??? none????
                    f.next_fetch_attempt = now + \
                        dt.timedelta(
                            seconds=random() * random_interval_mins * 60)
                    # maybe only log when verbosity > 0?
                    logger.info(f"CREATE {iid}")
                    create = True
                else:
                    # XXX check if queued????
                    # XXX check if modified_at has changed??
                    # maybe only log when verbosity > 0?
                    logger.info(f"UPDATE {iid}")
                    create = False

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

                    changes += check('created_at', 'created_at', ptime,
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
            log_stats(batch_stats)
        # end with session
        url = nxt
        if nxt:
            batch_stat("ok")
            time.sleep(sleep_time)
        break                   # TEMP
    # end while
    logger.error(f"Save last_modified={int(t0)}!!!")

    log_stats(batches, "BATCHES")
    log_stats(totals, "FEEDS")
    return 0


if __name__ == '__main__':
    SCRIPT = 'update_feeds'

    logger = logging.getLogger(SCRIPT)
    p = LogArgumentParser(SCRIPT, 'update feeds using CSV from mcweb')

    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    sys.exit(run())
