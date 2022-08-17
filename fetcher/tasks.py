import os
import datetime as dt
import requests
import feedparser
import json
from typing import Dict
import logging
import time
import hashlib
from sqlalchemy.exc import IntegrityError, PendingRollbackError
from psycopg2.errors import UniqueViolation
from celery import Task
from mcmetadata import urls

from fetcher import path_to_log_dir, SAVE_RSS_FILES
from fetcher.celery import app
from fetcher.database import Session
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
        'sourcesId': feed['sources_id'],
        'statusCode': response.status_code,
        'headers': dict(response.headers),
    }
    with open(os.path.join(RSS_FILE_LOG_DIR, "{}-summary.json".format(feed['sources_id'])), 'w',
              encoding='utf-8') as f:
        json.dump(summary, f, indent=4)
    with open(os.path.join(RSS_FILE_LOG_DIR, "{}-content.rss".format(feed['sources_id'])), 'w', encoding='utf-8') as f:
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
            self._session = Session()
        return self._session


def normalized_title_exists(session, normalized_title_hash: str, sources_id: int, day_window: int = 7) -> bool:
    if normalized_title_hash is None or sources_id is None:
        # err on the side of keeping URLs
        return False
    earliest_date = dt.date.today() - dt.timedelta(days=day_window)
    query = "select id from stories " \
            "where (published_at >= '{}'::DATE) AND (normalized_title_hash = :hash_title) and (sources_id=:sources_id)"\
        .format(earliest_date)
    with session.begin():
        matches = [r for r in session.execute(query, params=dict(hash_title=normalized_title_hash, sources_id=sources_id))]
    return len(matches) > 0


def normalized_url_exists(session, normalized_url: str) -> bool:
    if normalized_url is None:
        return False
    query = "select id from stories where (normalized_url = :normalized_url)"
    with session.begin():
        matches = [r for r in session.execute(query, params=dict(normalized_url=normalized_url))]
    return len(matches) > 0


def increment_fetch_failure_count(session, feed_id: int) -> int:
    with session.begin():
        f = session.query(models.Feed).get(feed_id)
        if f.last_fetch_failures is not None:
            f.last_fetch_failures += 1
        else:
            f.last_fetch_failures = 1
        new_value = f.last_fetch_failures
        session.commit()
        session.close()
    logger.info(" Feed {}: upped last_fetch_failure to {}".format(feed_id, new_value))
    return new_value


def save_fetch_event(session, feed_id: int, event: str, note: str):
    fe = models.FetchEvent.from_info(feed_id, event, note)
    with session.begin():
        session.add(fe)
        session.commit()
        session.close()


def _fetch_rss_feed(feed: Dict):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
    response = requests.get(feed['url'], headers=headers, timeout=RSS_FETCH_TIMEOUT_SECS)
    return response


def _parse_feed(session, feed_id: int, content: str):
    # try to parse the content parsing all the stories
    try:
        parsed_feed = feedparser.parse(content)
        if parsed_feed.bozo:
            raise RuntimeError(parsed_feed.bozo_exception)
        return parsed_feed
    except Exception as e:
        # BAIL: couldn't parse it correctly
        logger.warning("Couldn't parse feed: {}".format(str(e)))
        increment_fetch_failure_count(session, feed_id)
        save_fetch_event(session, feed_id, models.FetchEvent.EVENT_FETCH_FAILED,
                         "parse failure: {}".format(str(e)))


def fetch_feed_content(session, now: dt.datetime, feed: Dict):
    try:
        # first thing is to fetch the content
        logger.debug("Working on feed {}".format(feed['id']))
        response = _fetch_rss_feed(feed)
    # ignore fetch failure exceptions as a "normal operation" error
    except Exception as exc:
        logger.warning(" Feed {}: failed {}".format(feed['id'], exc))
        increment_fetch_failure_count(session, feed['id'])
        save_fetch_event(session, feed['id'], models.FetchEvent.EVENT_FETCH_FAILED, str(exc))
        return None
    # optional logging
    if SAVE_RSS_FILES:
        _save_rss_file(feed, response)
    # BAIL: HTTP failed
    if response.status_code != 200:
        logger.info("  Feed {} - skipping, bad response {} at {}".format(feed['id'], response.status_code, response.url))
        increment_fetch_failure_count(session, feed['id'])
        save_fetch_event(session, feed['id'], models.FetchEvent.EVENT_FETCH_FAILED,
                         "HTTP {} / {}".format(response.status_code, response.url))
        return None
    # Mark as a success because it responded with data
    new_hash = hashlib.md5(response.content).hexdigest()
    with session.begin():
        f = session.query(models.Feed).get(feed['id'])
        f.last_fetch_success = now
        f.last_fetch_hash = new_hash
        f.last_fetch_failures = 0
        session.commit()
    # BAIL: no changes since last time
    if new_hash == feed['last_fetch_hash']:
        logger.info("  Feed {} - skipping, same hash".format(feed['id']))
        save_fetch_event(session, feed['id'], models.FetchEvent.EVENT_FETCH_SUCCEEDED, "same hash")
        return None
    parsed_feed = _parse_feed(session, feed['id'], response.text)
    # update feed title (if it has one and it changed)
    with session.begin():
        f = session.query(models.Feed).get(feed['id'])
        if (parsed_feed is not None) and (len(parsed_feed.feed.title) > 0) and (f.name != parsed_feed.feed.title):
            f.title = parsed_feed.feed.title
            session.commit()
    return parsed_feed


def save_stories_from_feed(session, now: dt.datetime, feed: Dict, parsed_feed):
    # parsed OK, so insert all the (valid) entries
    skipped_count = 0
    for entry in parsed_feed.entries:
        try:
            if not util.is_absolute_url(entry.link):  # skip relative URLs
                logger.debug(" * skip relative URL: {}".format(entry.link))
                skipped_count += 1
                continue
            if urls.is_homepage_url(entry.link):
                logger.debug(" * skip homepage URL: {}".format(entry.link))
                skipped_count += 1
                continue
            s = models.Story.from_rss_entry(feed['id'], now, entry)
            s.sources_id = feed['sources_id']
            # only save if url is unique, and title is unique recently
            if not normalized_url_exists(session, s.normalized_url):
                if not normalized_title_exists(session, s.normalized_title_hash, s.sources_id):
                    # need to commit one by one so duplicate URL keys don't stop a larger insert from happening
                    # those are *expected* errors, so we can ignore them
                    with session.begin():
                        session.add(s)
                        session.commit()
                else:
                    logger.debug(" * skip duplicate title URL: {} | {} | {}".format(entry.link, s.normalized_title_hash, s.sources_id))
                    skipped_count += 1
            else:
                logger.debug(" * skip duplicate normalized URL: {} | {}".format(entry.link, s.normalized_url))
                skipped_count += 1
        except (AttributeError, KeyError) as exc:
            # couldn't parse the entry - skip it
            logger.debug("Missing something on rss entry {}".format(str(exc)))
            skipped_count += 1
        except (IntegrityError, PendingRollbackError, UniqueViolation) as _:
            # expected exception - log and ignore
            logger.debug(" * duplicate normalized URL: {}".format(s.normalized_url))
            skipped_count += 1

    logger.info("  Feed {} - {} entries ({} skipped)".format(feed['id'], len(parsed_feed.entries),
                                                             skipped_count))
    saved_count = len(parsed_feed.entries)-skipped_count
    save_fetch_event(session, feed['id'], models.FetchEvent.EVENT_FETCH_SUCCEEDED,
                     "{} entries / {} skipped / {} added".format(len(parsed_feed.entries),
                                                                 skipped_count,
                                                                 saved_count))
    return saved_count, skipped_count


@app.task(base=DBTask, serializer='json', bind=True)
def feed_worker(self, feed: Dict):
    """
    Fetch a feed, parse out stories, store them
    :param self: this maintains the single session to use for all DB operations
    :param feed: the feed to fetch
    """
    now = dt.datetime.now()
    parsed_feed = fetch_feed_content(self.session, now, feed)
    if parsed_feed is None:  # ie. valid content not fetched, so give up here
        return
    save_stories_from_feed(self.session, now, feed, parsed_feed)
