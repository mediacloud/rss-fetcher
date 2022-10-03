"""
This script run as `python -m scripts.queue_feeds`
from run-rss-workers.sh before starting celery workers
to allow starting in a 100% clean state
(nothing queued or marked as queued)
"""

import logging

from sqlalchemy import text

from fetcher.database import Session
from fetcher.queue import clear_work_queue
from fetcher.database.models import Feed

logger = logging.getLogger(__name__)

if __name__ == '__main__':
    # races possible; get table lock
    # NOTE: queuer updates table first, then queues

    with Session() as session:
        logger.info("Getting feeds table lock.")
        session.execute(text("LOCK TABLE feeds")) # for duration of transaction.
        logger.info("Locked.")

        logger.info("Purging work queue.")
        clear_work_queue()

        logger.info("Clearing Feed.queued column.")
        session.query(Feed).filter(Feed.queued == True)\
                           .update({'queued': False})

        logger.info("Committing.")
        session.commit() # releases lock
    logger.info("Done.")

