import os
import datetime as dt
import json
from typing import Dict
import logging
import time
import hashlib

# PyPI
import mcmetadata.urls
import requests
import feedparser
from sqlalchemy.exc import IntegrityError, PendingRollbackError
from psycopg2.errors import UniqueViolation
from celery import Task

# app
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
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
MAX_FAILURES = 3                # XXX get from environment?
DEFAULT_INTERVAL = 12*60*60

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


def update_feed(session, feed_id: int, success: bool, note: str,
                updates: dict = {},
                next_seconds: int = DEFAULT_INTERVAL):
    """
    update Feed row, insert FeedEvent row; MUST be called from all code paths!
    trying to make this the one place that updates the Feed row,
    and hopefully centralize policy
    """
    with session.begin():
        f = session.query(models.Feed).get(feed_id)

        f.queued = False        # safe to requeue
        if success:
            event = models.FetchEvent.EVENT_FETCH_SUCCEEDED
            # most success values come in via 'updates'
        else:
            event = models.FetchEvent.EVENT_FETCH_FAILED
            if f.last_fetch_failures is not None:
                failures = f.last_fetch_failures = f.last_fetch_failures + 1
            else:
                failures = f.last_fetch_failures = 1

            if failures >= MAX_FAILURES:
                f.system_enabled = False
                next_seconds = None
                logger.warning(f" Feed {feed_id}: disabled after {failures} failures")
            else:
                logger.info(f" Feed {feed_id}: upped last_fetch_failure to {failures}")
                # PLB: for backoff multiply next_seconds by failure count?!
                # would need a database column (set on success)
                # to base on interval suggested by feed

        if next_seconds is not None:
            f.next_fetch_attempt = models.utc(seconds=next_seconds)
            # PLB log new time?

        # apply additional updates (currently only used on success)
        # last, so can override default actions of this function.
        for key, value in updates:
            setattr(f, key, value)

        session.add(models.FetchEvent.from_info(feed_id, event, note))
        session.commit()
        session.close()

def _fetch_rss_feed(feed: Dict):
    headers = { 'User-Agent': USER_AGENT }

    etag = feed.get('http_etag', None)
    if etag:
        # If-None-Match takes one or more etag values
        headers['If-None-Match'] = etag # "value" or W/"value"
    else:
        # https://www.rfc-editor.org/rfc/rfc9110.html#name-if-modified-since says
        #     "A recipient MUST ignore If-Modified-Since if the request
        #     contains an If-None-Match header field"
        # The Internet credo is "be conservative in what you send"
        # so only sending one.
        lastmod = feed.get('http_last_modified', None)
        if lastmod:
            headers['If-Modified-Since'] = lastmod

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
        logger.warning(f"Couldn't parse feed: {e}")
        update_feed(session, feed_id, False, f"parse failure: {e}")
        return None

def fetch_feed_content(session, now: dt.datetime, feed: Dict):
    feed_id = feed['id']
    try:
        # first thing is to fetch the content
        logger.debug(f"Working on feed {feed_id}")
        response = _fetch_rss_feed(feed)
    # ignore fetch failure exceptions as a "normal operation" error
    except Exception as exc:
        logger.warning(f" Feed {feed_id}: failed {exc}")
        update_feed(session, feed_id, False, str(exc))
        return None
    # optional logging
    if SAVE_RSS_FILES:
        _save_rss_file(feed, response)

    # BAIL: HTTP failed (not full response or "Not Changed")
    if response.status_code != 200 and response.status_code != 304:
        logger.info(f"  Feed {feed_id} - skipping, bad response {response.status_code} at {response.url}")
        update_feed(session, feed_id, False,
                    f"HTTP {response.status_code} / {response.url}")
        return None

    # NOTE! 304 response will not have a body (terminated by end of headers)
    # so the last hash isn't (over)written below
    # (tho presumably if we get 304 responses, the next feed we get
    # will be different)
    new_hash = hashlib.md5(response.content).hexdigest()

    # Entity Tag may be W/"value" or "value", so keep as-is
    etag = response.headers.get('ETag', None)

    # kept unparsed; just sent back with If-Modified-Since.
    lastmod = response.headers.get('Last-Modified', None)

    # Mark as a success because it responded with data, or "not changed"
    updates = {'last_fetch_success': now,
               'last_fetch_failures': 0}

    # only save hash from full response (304 has no body)
    if response.status_code == 200:
        updates['last_fetch_hash'] = new_hash

    # https://www.rfc-editor.org/rfc/rfc9110.html#status.304
    # says a 304 response MUST have an ETag if 200 would have.
    # so always save it.
    updates['http_etag'] = etag

    # Last-Modified is not required in 304 response!
    if response.status_code == 200 or lastmod:
        updates['http_last_modified'] = lastmod

    # BAIL: server says file hasn't changed (no data returned) BEFORE looking at hash!!
    if response.status_code == 304:
        logger.info(f"  Feed {feed_id} - skipping, file not modified")
        update_feed(session, feed_id, True, "not modified", updates)
        return None

    # BAIL: no changes since last time
    if new_hash == feed['last_fetch_hash']:
        logger.info(f"  Feed {feed_id} - skipping, same hash")
        update_feed(session, feed_id, True, "same hash")
        return None

    parsed_feed = _parse_feed(session, feed_id, response.text)
    # update feed title (if it has one and it changed)
    try:
        with session.begin():
            f = session.query(models.Feed).get(feed_id)
            if (parsed_feed is not None) and (len(parsed_feed.feed.title) > 0) and (f.name != parsed_feed.feed.title):
                f.title = parsed_feed.feed.title
                session.commit()
    except AttributeError:
        # if the feed has no title that isn't really an error, just skip safely
        logger.debug(f"feed {feed_id} has no title")
        pass
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
            if mcmetadata.urls.is_homepage_url(entry.link):  # and skip very common homepage patterns
                logger.debug(" * skip homepage URL: {}".format(entry.link))
                skipped_count += 1
                continue
            s = models.Story.from_rss_entry(feed['id'], now, entry)
            # skip urls from high-quantity non-news domains we see a lot in feeds
            if s.domain in mcmetadata.urls.NON_NEWS_DOMAINS:
                logger.debug(" * skip non_news_domain URL: {}".format(entry.link))
                skipped_count += 1
                continue
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
        except (AttributeError, KeyError, ValueError, UnicodeError) as exc:
            # couldn't parse the entry - skip it
            logger.debug("Missing something on rss entry {}".format(str(exc)))
            skipped_count += 1
        except (IntegrityError, PendingRollbackError, UniqueViolation) as _:
            # expected exception - log and ignore
            logger.debug(" * duplicate normalized URL: {}".format(s.normalized_url))
            skipped_count += 1

    logger.info("  Feed {} - {} entries ({} skipped)".format(feed['id'], len(parsed_feed.entries),
                                                             skipped_count))
    ent = len(parsed_feed.entries)
    saved_count = ent-skipped_count
    update_feed(session, feed['id'], True,
                f"{ent} entries / {skipped_count} skipped / {saved_count} added")
    return saved_count, skipped_count


@app.task(base=DBTask, serializer='json', bind=True)
def feed_worker(self, feed_id: int):
    """
    Fetch a feed, parse out stories, store them
    :param self: this maintains the single session to use for all DB operations
    :param feed_id: integer Feed id
    """
    now = dt.datetime.now()

    # re-fetch row to avoid honoring time-sensitive data in queue.
    # with this in place, scripts/queue_feeds.py need only send id.

    if feed_id is None:
        # XXX PLB log??
        return

    session = self.session
    with session.begin():
        f = session.query(models.Feed).get(feed_id)
        if f is None:
            # XXX PLB log??
            return
        feed = f.as_dict()      # code expects dict

    parsed_feed = fetch_feed_content(session, now, feed)
    if parsed_feed is None:  # ie. valid content not fetched, so give up here
        return
    save_stories_from_feed(session, now, feed, parsed_feed)
