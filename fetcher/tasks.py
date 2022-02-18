import os
import datetime as dt
import requests
import feedparser
from typing import Dict
import logging
import time
import hashlib

from fetcher import path_to_log_dir
from fetcher.celery import app
import fetcher.database.queries as queries

logger = logging.getLogger(__name__)  # get_task_logger(__name__)
logFormatter = logging.Formatter("[%(levelname)s %(threadName)s] - %(asctime)s - %(name)s - : %(message)s")
fileHandler = logging.FileHandler(os.path.join(path_to_log_dir, "tasks-{}.log".format(time.strftime("%Y%m%d-%H%M%S"))))
fileHandler.setFormatter(logFormatter)
logger.addHandler(fileHandler)


RSS_FETCH_TIMEOUT_SECS = 30


@app.task(serializer='json', bind=True)
def feed_worker(self, feed: Dict):
    """
    Fetch a feed, parse out stories, store them
    :param self:
    :param feed:
    """
    try:
        logger.debug("Working on feed {}".format(feed['id']))
        fetched_at = dt.datetime.now()
        response = requests.get(feed['url'], timeout=RSS_FETCH_TIMEOUT_SECS)
        if response.status_code == 200:
            new_hash = hashlib.md5(response.content).hexdigest()
            if new_hash != feed['last_fetch_hash']:
                queries.update_last_fetch_success_hash(feed['id'], fetched_at, new_hash)
                parsed_feed = feedparser.parse(response.content)
                for entry in parsed_feed.entries:
                    queries.save_story_from_feed_entry(feed['id'], fetched_at, entry)
                logger.info("  Feed {} - {} entries".format(feed['id'], len(parsed_feed.entries)))
            else:
                logger.info("  Feed {} - skipping, same hash".format(feed['id']))
        else:
            logger.info("  Feed {} - skipping, bad response {}".format(feed['id'], response.status_code))
    except Exception as exc:
        # maybe we server didn't respond? ignore as normal operation perhaps?
        logger.error(" Feed {}: error: {}".format(feed['id'], exc))
