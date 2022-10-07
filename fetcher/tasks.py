# PLB ISSUES to be resolved:
# search for PLB!
# ESPECIALLY: when to pass feed_col_updates!!!!
# database columns w/ timezone?  run worker & PG server w/ TZ=UTC??!!!
# any times NOT to increment failure count??
# always pass feed_col_updates???

# PLB: cleanup WISHES
# convert all "".format calls to f""
# convert all feed['x'] to feed.x
# type hints for session objects
# type hints for void (-> None) functions
# create NewType for feeds_id?
# check type hints with mypy

import datetime as dt
import hashlib
import json
from numbers import Real
from typing import Dict, Tuple, Union
import logging
import os
import time

# PyPI
import feedparser
import mcmetadata.urls
from psycopg2.errors import UniqueViolation
import requests
from sqlalchemy.exc import IntegrityError, PendingRollbackError

# feed fetcher:
from fetcher import path_to_log_dir, DAY_WINDOW, DEFAULT_INTERVAL_MINS, \
    MAX_FAILURES, RSS_FETCH_TIMEOUT_SECS, SAVE_RSS_FILES
import fetcher.database.models as models
from fetcher.stats import Stats
import fetcher.queue
import fetcher.util as util

MINIMUM_INTERVAL_MINS = DEFAULT_INTERVAL_MINS # have separate param?

# shorthands:
FeedParserDict = feedparser.FeedParserDict

logger = logging.getLogger(__name__)  # get_task_logger(__name__)
logFormatter = logging.Formatter("[%(levelname)s %(threadName)s] - %(asctime)s - %(name)s - : %(message)s")
fileHandler = logging.FileHandler(os.path.join(path_to_log_dir, "tasks-{}.log".format(time.strftime("%Y%m%d-%H%M%S"))))
fileHandler.setFormatter(logFormatter)
logger.addHandler(fileHandler)

RSS_FILE_LOG_DIR = os.path.join(path_to_log_dir, "rss-files")
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'

# RDF Site Summary 1.0 Modules: Syndication
# https://web.resource.org/rss/1.0/modules/syndication/
_DAY_MINS = 24*60
UPDATE_PERIODS_MINS = {
    'hourly': 60,
    'daily': _DAY_MINS,
    'dayly': _DAY_MINS,  # http://cuba.cu/feed & http://tribuna.cu/feed
    'weekly': 7*_DAY_MINS,
    'monthly': 30*_DAY_MINS,
    'yearly': 365*_DAY_MINS,
}
DEFAULT_UPDATE_PERIOD = 'daily' # specified in Syndication spec
DEFAULT_UPDATE_FREQUENCY = 1    # specified in Syndication spec

def _save_rss_file(feed: Dict, response):
    # debugging helper method - saves two files for the feed to /logs/rss-feeds
    summary = {
        'id': feed['id'],
        'url': feed['url'],
        'sourcesId': feed['sources_id'],
        'statusCode': response.status_code,
        'headers': dict(response.headers),
    }
    # PLB: only saves one feed per source? bug and feature!
    with open(os.path.join(RSS_FILE_LOG_DIR, "{}-summary.json".format(feed['sources_id'])), 'w',
              encoding='utf-8') as f:
        json.dump(summary, f, indent=4)
    with open(os.path.join(RSS_FILE_LOG_DIR, "{}-content.rss".format(feed['sources_id'])), 'w', encoding='utf-8') as f:
        f.write(response.text)


def normalized_title_exists(session, normalized_title_hash: str,
                            sources_id: int,
                            day_window: int = DAY_WINDOW) -> bool:
    if normalized_title_hash is None or sources_id is None:
        # err on the side of keeping URLs
        return False
    earliest_date = dt.date.today() - dt.timedelta(days=day_window)
    with session.begin():
        return session.query(
            models.Story.query.filter(
                models.Story.published_at >= earliest_date,
                models.Story.normalized_title_hash == normalized_title_hash,
                models.Story.sources_id == sources_id
            ).exists()
        ).scalar()

def normalized_url_exists(session, normalized_url: str) -> bool:
    if normalized_url is None:
        return False
    with session.begin():
        return session.query(
            models.Story.query.filter(
                models.Story.normalized_url == normalized_url
            ).exists()
        ).scalar()


def update_feed(session, feed_id: int, success: bool, note: str,
                feed_col_updates: Union[Dict,None] = None):
    """
    Update Feed row, insert FeedEvent row; MUST be called from all
    feed_worker code paths in order to clear "queued" and update
    "next_fetch_attempt"!!!

    Trying to make this the one place that updates the Feed row,
    so all policy can be centralized here.
    """

    # PLB log w/note?? likely makes numerous other log messages redundant!
    with session.begin():
        # NOTE! locks row, so update atomic.
        # (atomic increment IS possible without this,
        # but we want to make choices based on the new value)
        f = session.get(models.Feed, feed_id, with_for_update=True)
        if f is None:
            log.info(f"  Feed {feed_id} not found in update_feed")
            return

        # apply additional updates first to simplify checks
        if feed_col_updates:
            for key, value in feed_col_updates.items():
                setattr(f, key, value)

        f.queued = False        # safe to requeue

        # get normal feed update period in minutes, one of:
        # 1. new value being passed in to update Feed row (from RSS)
        # 2. value currently stored in feed row (if fetch or parse failed)
        # 3. default
        # (update_minutes is either a value from feed, or NULL)
        next_minutes = f.update_minutes or DEFAULT_INTERVAL_MINS

        if success:
            event = models.FetchEvent.EVENT_FETCH_SUCCEEDED
            f.last_fetch_failures = 0
            # many values come in via 'feed_col_updates'

            # PLB: save "working" as system_status??
        else:
            failures = f.last_fetch_failures = f.last_fetch_failures + 1

            if failures >= MAX_FAILURES:
                event = models.FetchEvent.EVENT_FETCH_FAILED_DISABLED
                f.system_enabled = False
                next_minutes = None # don't reschedule
                logger.warning(f" Feed {feed_id}: disabled after {failures} failures")
                # PLB: save "disabled" as system_status????
            else:
                event = models.FetchEvent.EVENT_FETCH_FAILED
                logger.info(f" Feed {feed_id}: upped last_fetch_failure to {failures}")

                # back off to be kind to servers:
                # linear backoff (ie; 12h, 1d, 1.5d, 2d)
                next_minutes *= failures

                # exponential backoff:
                # kinder, but excessive delays with long initial period.
                # (ie; 12h, 1d, 2d, 4d)
                #next_minutes *= 2 ** (failures - 1)

            # PLB: save note as f.system_status??
            # (split w/ " / " and/or ":" and save front part)???
            # or pass note in two halves: system_status & detail????

        if next_minutes is not None: # reschedule?
            if next_minutes < MINIMUM_INTERVAL_MINS:
                next_minutes = MINIMUM_INTERVAL_MINS # clamp to minimum
            f.next_fetch_attempt = next_dt = models.utc(seconds=next_minutes*60)
            logger.debug(f"  Feed {feed_id} rescheduled for {next_dt}")
        elif f.system_enabled:
            logger.error("  Feed {feed_id} enabled but not rescheduled!")

        # PLB: use now value from top level fetch_and_process_feed
        #   so matches up with Story (and Feed.last_fetch_success)??
        session.add(models.FetchEvent.from_info(feed_id, event, note))
        session.commit()
        session.close()

def _feed_update_period_mins(parsed_feed: FeedParserDict) -> Union[None, Real]:
    """
    Extract feed update period in minutes, if any from parsed feed.
    Returns None if <sy:updatePeriod> not present, or bogus in some way.
    """
    try:
        pff = parsed_feed.feed
        # (spec says default to 24h, but our current default is less,
        # so only process if tag present (which SHOULD manifest
        # as a string value, even if empty, in which case applying
        # the default is reasonable) and None if tag not present
        update_period = pff.get('sy_updateperiod')
        if update_period is None: # tag not present
            return None

        # translate string to value: empty string (or pure whitespace)
        # is treated as DEFAULT_UPDATE_PERIOD
        update_period = update_period.strip().rstrip()
        upm = UPDATE_PERIODS_MINS.get(update_period or DEFAULT_UPDATE_PERIOD)
        # *should* get here with a value (unless DEFAULT_UPDATE_PERIOD is bad)

        #logger.debug(f" update_period {update_period} upm {upm}")

        # get divisor.  use default if not present or empty, or whitespace only
        update_frequency = pff.get('sy_updatefrequency')
        if update_frequency is not None:
            # translate to number: have seen 0.1 as update_frequency!
            ufn = float(update_frequency.strip() or DEFAULT_UPDATE_FREQUENCY)
            #logger.debug(f" update_frequency {update_frequency} ufn {ufn}")
            if ufn <= 0.0:
                return None     # treat as missing tags
        else:
            ufn = DEFAULT_UPDATE_FREQUENCY

        ret = int(upm / ufn)    # XXX never return zero?
        #logger.debug(f" _feed_update_period_mins pd {update_period} fq {update_frequency} => {ret}")
        return ret
    except:
        #logger.exception("_feed_update_period_mins") # DEBUG
        return None

def _fetch_rss_feed(feed: Dict) -> requests.Response:
    """
    Fetch current feed document using Feed.url
    may add headers that make GET conditional (result in 304 status_code).
    Raises exceptions on errors
    """
    headers = { 'User-Agent': USER_AGENT }

    # if ETag (Entity-Tag) stashed, make GET conditional
    etag = feed.get('http_etag', None)
    if etag:
        # If-None-Match takes one or more etag values
        headers['If-None-Match'] = etag # "value" or W/"value"
    else:
        # if no ETag, but have an old Last-Modified header value
        # make GET conditional on THAT.
        # https://www.rfc-editor.org/rfc/rfc9110.html#name-if-modified-since
        # says:
        #     "A recipient MUST ignore If-Modified-Since if the request
        #     contains an If-None-Match header field"
        # The Internet credo is "be conservative in what you send"
        # so only sending one.
        lastmod = feed.get('http_last_modified', None)
        if lastmod:
            headers['If-Modified-Since'] = lastmod

    response = requests.get(feed['url'], headers=headers, timeout=RSS_FETCH_TIMEOUT_SECS)
    return response


def fetch_and_process_feed(session, feed_id: int):
    """
    Was fetch_feed_content: this is THE routine called in a worker.
    Made a single routine for clarity/communication
    (communication could be eased by encapsulating as a class)
    ALL exits from this function should call `update_feed` to:
    * clear "Feed.queued"
    * create FetchEvent row
    * increment or clear Feed.last_fetch_failure
    * update Feed.next_fetch_attempt (or not) to reschedule
    """

    stats = Stats.get()
    def feeds_incr(status):
        """call exactly ONCE for each feed processed"""
        stats.incr('feeds', 1, labels=[['stat', status]])

    # used in Feed.last_fetch_success, Story.fetched_at (but not FetchEntry)
    now = dt.datetime.utcnow()

    with session.begin():
        f = session.get(models.Feed, feed_id)
        if f is None:
            feeds_incr('missing')
            logger.info(f"feed_worker: feed {feed_id} not found")
            return

        # sanity checks, in case entry modified while in queue
        # (including being queued more than once)
        # Driftwood (Groucho):
        #   It's all right. That's, that's in every contract.
        #   That's, that's what they call a sanity clause.
        # Fiorello (Chico):
        #   Ha-ha-ha-ha-ha! You can't fool me.
        #   There ain't no Sanity Clause!
        # Marx Brothers' "Night at the Opera" (1935)
        if (not f.active or not f.system_enabled or
            not f.queued or f.next_fetch_attempt > now):
            feeds_incr('insane')

            logger.info(f"insane: act {f.active} ena {f.system_enabled} qd {f.queued} nxt {f.next_fetch_attempt}")
            return
        feed = f.as_dict()      # code expects dict PLB: fix?

    try:
        # first thing is to fetch the content
        logger.debug(f"Working on feed {feed_id}")
        response = _fetch_rss_feed(feed)
    except Exception as exc:
        # ignore fetch failure exceptions as a "normal operation" error
        # XXX PLB does this mean no failure count increment?
        logger.warning(f" Feed {feed_id}: fetch failed {exc}")
        update_feed(session, feed_id, False, f"fetch: {exc}")

        # NOTE!! try to limit cardinality of status: (eats stats storage)
        # so not doing detailed breakdown for starters (full info
        # available in fetch_event rows).
        es = str(exc)
        if 'ConnectionPool' in es: # use isinstance??
            feeds_incr('conn_err')
        else:
            feeds_incr('fetch_err')
        return

    if SAVE_RSS_FILES:
        _save_rss_file(feed, response)

    # BAIL: HTTP failed (not full response or "Not Changed")
    if response.status_code != 200 and response.status_code != 304:
        logger.info(f"  Feed {feed_id} - skipping, bad response {response.status_code} at {response.url}")
        update_feed(session, feed_id, False,
                    f"HTTP {response.status_code} / {response.url}")

        # limiting tag cardinality, only a few, common codes for now.
        # NOTE! 429 is "too many requests" (ie; slow down)
        # It's possible 403 is also used that way???
        if response.status_code in (403, 404, 429):
            feeds_incr(f"http_{response.status_code}")
        else:
            feeds_incr(f"http_{response.status_code//100}xx")
        return

    # NOTE! 304 response will not have a body (terminated by end of headers)
    # so the last hash isn't (over)written below
    # (tho presumably if we get 304 responses, the next feed we get
    # will be different)
    new_hash = hashlib.md5(response.content).hexdigest()

    # Entity Tag may be W/"value" or "value", so keep as-is
    etag = response.headers.get('ETag', None)

    # kept unparsed; just sent back with If-Modified-Since.
    lastmod = response.headers.get('Last-Modified', None)

    # responded with data, or "not changed", so update last_fetch_success
    feed_col_updates = {
        'last_fetch_success': now, # HTTP fetch succeeded
    }

    # NOTE!!! feed_col_updates only currently used on "success",
    # if feed processing stopped by a bug in our code, we will
    # try again with unchanged data after the bug is fixed,
    # and the feed is reenabled.

    # https://www.rfc-editor.org/rfc/rfc9110.html#status.304
    # says a 304 response MUST have an ETag if 200 would have.
    # so always save it (even if that means NULLing it out)
    feed_col_updates['http_etag'] = etag

    # Last-Modified is not required in 304 response!
    # always save on 200 (even if that means NULLing it out)
    if response.status_code == 200 or lastmod:
        feed_col_updates['http_last_modified'] = lastmod

    # BAIL: server says file hasn't changed (no data returned)
    if response.status_code == 304:
        logger.info(f"  Feed {feed_id} - skipping, file not modified")
        # PLB feed_col_updates??
        update_feed(session, feed_id, True, "not modified", feed_col_updates)
        feeds_incr('not_mod')
        return

    # BAIL: no changes since last time
    if new_hash == feed['last_fetch_hash']:
        logger.info(f"  Feed {feed_id} - skipping, same hash")
        # PLB feed_col_updates??
        update_feed(session, feed_id, True, "same hash", feed_col_updates)
        feeds_incr('same_hash')
        return

    # PLB: log error if here w/o status_code == 200?
    feed_col_updates['last_fetch_hash'] = new_hash

    # try to parse the content, parsing all the stories
    try:
        parsed_feed = feedparser.parse(response.text)
        if parsed_feed.bozo:
            raise RuntimeError(parsed_feed.bozo_exception)
    except Exception as e:
        # BAIL: couldn't parse it correctly
        logger.warning(f"Couldn't parse feed {feed_id}: {e}")
        update_feed(session, feed_id, False, f"parse: {e}")
        # split up into different counters if needed/desired
        # (beware label cardinality)
        feeds_incr('parse_err')
        return

    feeds_incr('ok')

    saved, skipped = save_stories_from_feed(session, now, feed, parsed_feed)

    # may update feed_col_updates dict:
    check_feed_title(feed, parsed_feed, feed_col_updates)

    # see if feed indicates update period
    try:                        # paranoia
        update_period_mins = _feed_update_period_mins(parsed_feed)

        if update_period_mins is not None:
            period_str = dt.timedelta(seconds=update_period_mins*60)
            logger.debug(f"  Feed {feed_id} update period {period_str}")
    except:
        logger.exception("update period") # XXX debug only?
        update_period_mins = None

    feed_col_updates['update_minutes'] = update_period_mins
    update_feed(session, feed_id, True, f"{skipped} skipped / {saved} added",
               feed_col_updates)

def save_stories_from_feed(session, now: dt.datetime, feed: Dict,
                           parsed_feed: FeedParserDict) -> Tuple[int,int]:
    """
    Take parsed feed, so insert all the (valid) entries.
    returns (saved_count, skipped_count)
    """
    stats = Stats.get()
    def stories_incr(status):
        """call exactly ONCE for each story processed"""
        stats.incr('stories', 1, labels=[['stat', status]])

    skipped_count = 0
    for entry in parsed_feed.entries:
        try:
            if not util.is_absolute_url(entry.link):  # skip relative URLs
                logger.debug(" * skip relative URL: {}".format(entry.link))
                stories_incr('relurl')
                skipped_count += 1
                continue
            if mcmetadata.urls.is_homepage_url(entry.link):  # and skip very common homepage patterns
                logger.debug(" * skip homepage URL: {}".format(entry.link))
                stories_incr('home')
                skipped_count += 1
                continue
            s = models.Story.from_rss_entry(feed['id'], now, entry)
            # skip urls from high-quantity non-news domains we see a lot in feeds
            if s.domain in mcmetadata.urls.NON_NEWS_DOMAINS:
                logger.debug(" * skip non_news_domain URL: {}".format(entry.link))
                stories_incr('nonews')
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
                    stories_incr('ok')
                else:
                    logger.debug(" * skip duplicate title URL: {} | {} | {}".format(entry.link, s.normalized_title_hash, s.sources_id))
                    stories_incr('dup_title')
                    skipped_count += 1
            else:
                logger.debug(" * skip duplicate normalized URL: {} | {}".format(entry.link, s.normalized_url))
                stories_incr('dup_url')
                skipped_count += 1
        except (AttributeError, KeyError, ValueError, UnicodeError) as exc:
            # couldn't parse the entry - skip it
            logger.debug("Missing something on rss entry {}".format(str(exc)))
            stories_incr('bad')
            skipped_count += 1
        except (IntegrityError, PendingRollbackError, UniqueViolation) as _:
            # expected exception - log and ignore
            logger.debug(" * duplicate normalized URL: {}".format(s.normalized_url))
            stories_incr('dupurl2')
            skipped_count += 1

    entries = len(parsed_feed.entries)
    logger.info(f"  Feed {feed['id']} - {entries} entries ({skipped_count} skipped)")
    saved_count = entries - skipped_count
    return saved_count, skipped_count


def check_feed_title(feed: Dict, parsed_feed: FeedParserDict,
                           feed_col_updates: Dict):
    # update feed title (if it has one and it changed)
    try:
        title = parsed_feed.feed.title
        if len(title) > 0:
            title = ' '.join(title.split()) # condense whitespace

            if title and feed['name'] != title:
                # use !r (repr) to display strings w/ quotes
                logger.info(f" Feed {feed['id']} updating name from {feed['name']!r} to {title!r}")
                feed_col_updates['name'] = title
    except AttributeError:
        # if the feed has no title that isn't really an error, just skip safely
        pass
    except:
        # not REALLY worth pulling a fire alarm over, but still
        # should be fixed!
        logger.exception("check_feed_title")

################


# NOTE! RQ has a job decorator, but not using it to avoid
# needing to fetch config at include time, so logging can be controlled better.
# NOTE!!! MUST be run from SimpleWorker to achieve session caching!!!!
# XXX maybe queue feed_id and date/time used to set last_fetch_attempt when queued?
def feed_worker(feed_id: int):
    """
    Fetch a feed, parse out stories, store them
    :param self: this maintains the single session to use for all DB operations
    :param feed_id: integer Feed id
    """
    session = fetcher.queue.get_session()

    # XXX setproctitle(f"{APP} worker feed {feed_id}")???

    # for total paranoia, wrap in try, call update_feed on exception??
    fetch_and_process_feed(session, feed_id)
