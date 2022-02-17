import logging
import datetime as dt

import fetcher.database.queries as queries
import fetcher.tasks as tasks

MAX_FEEDS = 10

if __name__ == '__main__':

    logger = logging.getLogger(__name__)
    logger.info("Starting Feed Queuer")

    feeds_to_check = queries.feeds_to_check(MAX_FEEDS)
    for f in feeds_to_check:
        queries.update_last_fetch_attempt(f['id'], dt.datetime.now())
        tasks.feed_worker.delay(f)

    logger.info("  queued {} feeds".format(len(feeds_to_check)))
