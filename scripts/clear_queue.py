"""
This script run as `python -m scripts.queue_feeds`
from run-rss-workers.sh before starting celery workers
"""

import logging

from fetcher.database import Session
from fetcher.celery import app
from fetcher.database.models import Feed

logger = logging.getLogger(__name__)

if __name__ == '__main__':
    # races possible; get table lock
    # NOTE: queuer updates table first, then queues

    with Session() as session:
        logger.info("Getting feeds table lock.")
        session.execute("LOCK TABLE feeds") # for duration of transaction.
        logger.info("Locked.")

        logger.info("Purging celery queue.")
        app.control.purge()

        logger.info("Clearing Feed.queued column.")
        session.query(Feed).filter(Feed.queued == True)\
                           .update({'queued': False})

        logger.info("Committing.")
        session.commit() # releases lock
    logger.info("Done.")

