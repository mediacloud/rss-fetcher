"""
Read CSV dumped from mcweb-db sources_feed table to update our feeds table.
(run by dokku-scripts/sync-feeds.sh from /etc/cron.d/rss-fetcher)
"""

import csv
import datetime as dt
import logging
from random import random       # low-fi random ok

from fetcher.config import conf
from fetcher.database import Session
import fetcher.database.models as models
from fetcher.logargparse import LogArgumentParser


def ptime(s: str) -> dt.datetime:
    # XXX handle non-zero TZ?
    return dt.datetime.strptime(s, '%Y-%m-%d %H:%M:%S.%f+00')

if __name__ == '__main__':
    SCRIPT = 'update_feeds'

    logger = logging.getLogger(SCRIPT)
    p = LogArgumentParser(SCRIPT, 'update feeds using CSV from mcweb')

    # mandatory positional argument
    p.add_argument('input_file', metavar='INPUT_FILE')

    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    DEFAULT_INTERVAL_MINS = conf.DEFAULT_INTERVAL_MINS

    # import data
    filename = args.input_file
    logger.info(f"Importing from {filename}")
    if filename.endswith(".gz"):
        import gzip
        f = gzip.open(filename, mode='rt')  # read in text mode
    else:
        f = open(filename)
    input_file = csv.DictReader(f)

    created = updated = 0
    now = dt.datetime.utcnow()
    with Session.begin() as session:  # type: ignore[attr-defined]
        for row in input_file:
            iid = int(row['id'])
            f = session.get(models.Feed, iid)
            if f is None:
                f = models.Feed()
                f.id = iid

                f.next_fetch_attempt = now + \
                    dt.timedelta(seconds=random() * DEFAULT_INTERVAL_MINS * 60)
                created += 1
            else:
                updated += 1

            f.url = row['url']
            f.sources_id = int(row['source_id'])  # note names differ
            f.active = row['admin_rss_enabled'][0] == 't'
            f.created_at = ptime(row['created_at'])

            # XXX may have been updated by fetcher from feed!!!!
            f.name = row['name']

            # ignoring modified_at, but if saved could be used for
            # MAX(mcweb_modified_at) to know most recent update fetched.

            session.add(f)
        session.commit()
    logger.info(f"created {created}, updated {updated}")
