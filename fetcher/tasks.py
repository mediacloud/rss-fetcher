import os
import datetime as dt
import requests
import feedparser
from typing import Dict
import logging
import time
import hashlib
from sqlalchemy.exc import IntegrityError

from fetcher import path_to_log_dir
from fetcher.celery import app
from fetcher.database import Session, engine
import fetcher.database.models as models
import fetcher.util as util

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
        worked = False  # did we fetch a file successfully?
        logger.debug("Working on feed {}".format(feed['id']))
        fetched_at = dt.datetime.now()
        response = requests.get(feed['url'], timeout=RSS_FETCH_TIMEOUT_SECS)
        if response.status_code == 200:
            new_hash = hashlib.md5(response.content).hexdigest()
            # try to reduce overall connection churn by holding one connection per task
            with engine.connect() as connection:  # will call close automatically
                # first mark the success
                with Session(bind=connection) as session:
                    f = session.query(models.Feed).get(feed['id'])
                    f.last_fetch_success = fetched_at
                    f.last_fetch_hash = new_hash
                    f.last_fetch_failures = 0
                    session.commit()
                    worked = True
                # now that we've marked that it worked, parse the stories (if it is a new file)
                if new_hash != feed['last_fetch_hash']:
                    parsed_feed = feedparser.parse(response.content)
                    skipped_count = 0
                    for entry in parsed_feed.entries:
                        if not util.is_absolute_url(entry.link):  # skip relative URLs
                            logger.debug(" * skip relative URL: {}".format(entry.link))
                            continue
                        s = models.Story.from_rss_entry(feed['id'], fetched_at, entry)
                        s.media_id = feed['mc_media_id']
                        if not s.title_already_exists():  # only save if title is unique recently
                            # need to commit one by one so duplicate URL keys don't stop a larger insert from happening
                            # those are *expected* errors, so we can ignore them
                            with Session(bind=connection) as session:
                                try:
                                    session.add(s)
                                    session.commit()
                                except IntegrityError as _:
                                    logger.debug(" * duplicate normalized URL: {}".format(s.normalized_url))
                                    skipped_count += 1
                    logger.info("  Feed {} - {} entries ({} skipped)".format(feed['id'], len(parsed_feed.entries),
                                                                             skipped_count))
                else:  # not a new file (failed hash check)
                    logger.info("  Feed {} - skipping, same hash".format(feed['id']))
        else:  # HTTP fail
            logger.info("  Feed {} - skipping, bad response {}".format(feed['id'], response.status_code))
    # ignore fetch failure exceptions as a "normal operation" error
    except Exception as exc:
        # maybe the server didn't respond? ignore as normal operation perhaps?
        logger.info(" Feed {}: failed {}".format(feed['id'], exc))
    # but also mark when things haven't worked
    if not worked:
        with engine.connect() as connection:  # will call close automatically
            with Session(bind=connection) as session:
                f = session.query(models.Feed).get(feed['id'])
                if f.last_fetch_failures is not None:
                    f.last_fetch_failures += 1
                else:
                    f.last_fetch_failures = 1
                session.commit()
                logger.info(" Feed {}: upped last_fetch_failure to {}".format(feed['id'], f.last_fetch_failures))
