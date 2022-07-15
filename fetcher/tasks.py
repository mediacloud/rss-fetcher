import os
import datetime as dt
import requests
import feedparser
import json
from typing import Dict
import logging
import copy
import time
import hashlib
from sqlalchemy.exc import IntegrityError
from celery import Task

from fetcher import path_to_log_dir, SAVE_RSS_FILES
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
RSS_FILE_LOG_DIR = os.path.join(path_to_log_dir, "rss-files")


def _save_rss_file(feed: Dict, response):
    # debugging helper method - saves two files for the feed to /logs/rss-feeds
    summary = {
        'id': feed['id'],
        'url': feed['url'],
        'mcFeedsId': feed['mc_feeds_id'],
        'mcMediaId': feed['mc_media_id'],
        'statusCode': response.status_code,
        'headers': dict(response.headers),
    }
    with open(os.path.join(RSS_FILE_LOG_DIR, "{}-summary.json".format(feed['mc_media_id'])), 'w',
              encoding='utf-8') as f:
        json.dump(summary, f, indent=4)
    with open(os.path.join(RSS_FILE_LOG_DIR, "{}-content.rss".format(feed['mc_media_id'])), 'w', encoding='utf-8') as f:
        f.write(response.text)


# Try to reduce DB session pool churn by using one session per tasks, and returning it to the pool when task is done
# https://stackoverflow.com/questions/31999269/how-to-setup-sqlalchemy-session-in-celery-tasks-with-no-global-variable
class DBTask(Task):
    _session = None

    def after_return(self, *args, **kwargs):
        if self._session is not None:
            self._session.commit()  # just in case
            self._session.close()

    @property
    def session(self):
        if self._session is None:
            connection = engine.connect()
            self._session = Session(bind=connection)
        return self._session


def title_already_exists(session, normalized_title_hash: str, media_id: int, day_window: int = 7) -> bool:
    if normalized_title_hash is None or media_id is None:
        # err on the side of keeping URLs
        return False
    earliest_date = dt.date.today() - dt.timedelta(days=day_window)
    query = "select id from stories " \
            "where (published_at >= '{}'::DATE) AND (normalized_title_hash = '{}') and (media_id={})"\
        .format(earliest_date, normalized_title_hash, media_id)
    matches = [r for r in session.execute(query)]
    return len(matches) > 0


def increment_fetch_failure_count(session, feed_id: int) -> int:
    f = session.query(models.Feed).get(feed_id)
    if f.last_fetch_failures is not None:
        f.last_fetch_failures += 1
    else:
        f.last_fetch_failures = 1
    session.commit()
    logger.info(" Feed {}: upped last_fetch_failure to {}".format(feed_id, f.last_fetch_failures))
    return f.last_fetch_failures


def _fetch_rss_feed(feed: Dict):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
    response = requests.get(feed['url'], headers=headers, timeout=RSS_FETCH_TIMEOUT_SECS)
    return response


@app.task(base=DBTask, serializer='json', bind=True)
def feed_worker(self, feed: Dict):
    """
    Fetch a feed, parse out stories, store them
    :param self: this maintains the single session to use for all DB operations
    :param feed: the feed to fetch
    """
    try:
        # first thin is to fetch the content
        logger.debug("Working on feed {}".format(feed['id']))
        fetched_at = dt.datetime.now()
        response = _fetch_rss_feed(feed)
    # ignore fetch failure exceptions as a "normal operation" error
    except Exception as exc:
        logger.warning(" Feed {}: failed {}".format(feed['id'], exc))
        increment_fetch_failure_count(self.session, feed['id'])
        fe = models.FetchEvent.from_info(feed['id'], models.FetchEvent.EVENT_FETCH_FAILED, str(exc))
        self.session.add(fe)
        self.session.commit()
        return
    # optional logging
    if SAVE_RSS_FILES:
        _save_rss_file(feed, response)
    # BAIL: HTTP failed
    if response.status_code != 200:
        logger.info("  Feed {} - skipping, bad response {} at {}".format(feed['id'], response.status_code, response.url))
        increment_fetch_failure_count(self.session, feed['id'])
        fe = models.FetchEvent.from_info(feed['id'], models.FetchEvent.EVENT_FETCH_FAILED,
                                         "HTTP {} / {}".format(response.status_code, response.url))
        self.session.add(fe)
        self.session.commit()
        return
    # Mark as a success because it responded with data
    new_hash = hashlib.md5(response.content).hexdigest()
    f = self.session.query(models.Feed).get(feed['id'])
    f.last_fetch_success = fetched_at
    f.last_fetch_hash = new_hash
    f.last_fetch_failures = 0
    self.session.commit()
    # BAIL: no changes since last time
    if new_hash == feed['last_fetch_hash']:
        logger.info("  Feed {} - skipping, same hash".format(feed['id']))
        fe = models.FetchEvent.from_info(feed['id'], models.FetchEvent.EVENT_FETCH_SUCCEEDED,
                                         "same hash")
        self.session.add(fe)
        self.session.commit()
        return
    # worth parsing all the stories
    parsed_feed = feedparser.parse(response.content)
    skipped_count = 0
    for entry in parsed_feed.entries:
        try:
            if not util.is_absolute_url(entry.link):  # skip relative URLs
                logger.debug(" * skip relative URL: {}".format(entry.link))
                skipped_count += 1
                continue
            s = models.Story.from_rss_entry(feed['id'], fetched_at, entry)
            s.media_id = feed['mc_media_id']
            # only save if title is unique recently
            if not title_already_exists(self.session, s.normalized_title_hash, s.media_id):
                # need to commit one by one so duplicate URL keys don't stop a larger insert from happening
                # those are *expected* errors, so we can ignore them
                self.session.add(s)
                self.session.commit()
        except (AttributeError, KeyError) as exc:
            # couldn't parse the entry - skip it
            logger.debug("Missing something on rss entry {}".format(str(exc)))
            skipped_count += 1
        except IntegrityError as _:
            # expected exception - log and ignore
            logger.debug(" * duplicate normalized URL: {}".format(s.normalized_url))
            skipped_count += 1
    logger.info("  Feed {} - {} entries ({} skipped)".format(feed['id'], len(parsed_feed.entries),
                                                             skipped_count))
    fe = models.FetchEvent.from_info(feed['id'], models.FetchEvent.EVENT_FETCH_SUCCEEDED,
                                     "{} entries / {} skipped / {} added".format(len(parsed_feed.entries),
                                                                                 skipped_count,
                                                                                 len(parsed_feed.entries)-skipped_count))
    self.session.add(fe)
    self.session.commit()

