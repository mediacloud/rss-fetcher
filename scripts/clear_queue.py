"""
run this as a script `python -m scripts.queue_feeds`
before starting celery workers
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
        logger.info("Locking feeds table.")
        session.execute("LOCK TABLE feeds") 

        logger.info("Purging celery queue.")
        app.control.purge()

        logger.info("Clearing Feed.queued column.")
        session.query(Feed).filter(Feed.queued == True).update({'queued': False})

        logger.info("Done.")
        session.commit() # releases lock

