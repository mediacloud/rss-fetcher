import logging
import datetime as dt

import fetcher.database.queries as queries
import fetcher.tasks as tasks

MAX_FEEDS = 10000

if __name__ == '__main__':

    logger = logging.getLogger(__name__)
    logger.info("Starting Feed Queuer")

    feed_count = 0
    for f in queries.process_feeds_to_check(MAX_FEEDS):
        queries.update_last_fetch_attempt(f['id'], dt.datetime.now())
        tasks.feed_worker.delay(f)
        feed_count += 1

    logger.info("  queued {} feeds".format(feed_count))
