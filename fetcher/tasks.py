"""
Code for tasks run in worker processes.
(when celery was used for parallel task execution the
file name was mandatory)

NOTE!! Great effort has been made to avoid catching all exceptions all
over the place because queued tasks can be interrupted by a
JobTimeoutException.
"""

import datetime as dt
import hashlib
import http.client
import json
import logging
import logging.handlers
import os
import random
import time
import warnings
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, NamedTuple, Optional, Tuple, cast
from urllib.parse import urlsplit

# PyPI
import feedparser
# from sitemap-tools
import mc_sitemap_tools.parser as sitemap_parser
import mcmetadata.titles as titles
import mcmetadata.urls
import mcmetadata.urls as urls
import requests
import requests.exceptions
import sqlalchemy.sql.functions as func  # avoid overriding "sum"
from mcmetadata.requests_arcana import insecure_requests_session
from mcmetadata.webpages import MEDIA_CLOUD_USER_AGENT
from psycopg.errors import UniqueViolation
# NOTE! All references to rq belong in queue.py!
from sqlalchemy import literal, select
from sqlalchemy.exc import IntegrityError, PendingRollbackError
from urllib3.exceptions import InsecureRequestWarning

import fetcher.path as path
import fetcher.util as util
# feed fetcher:
from fetcher.config import conf
from fetcher.database import Session, SessionType
from fetcher.database.models import Feed, FetchEvent, Story, utc
from fetcher.direct import JobTimeoutException, set_job_timeout
from fetcher.headhunter import Item
from fetcher.stats import Stats

# Increase Python3 http header limit (default is 100):
setattr(http.client, '_MAXHEADERS', 1000)


# set of field_col_changes fields to log at info (else log at debug)
LOG_AT_INFO = {'update_minutes', 'rss_title'}


# take twice as many soft failures to disable feed
# to lessen spurrious disabling due to transient/human errors.
SOFT_FAILURE_INCREMENT = 0.5


# non-zero, in case permanent!
TEMP_FAILURE_INCREMENT = 0.25


class DupPct:
    """
    synthetic dup_pct values passed to _check_auto_adjust_longer
    (All above 100%)

    Values **NOT** intended to be used for comparison (ie; as "magic"
    values), which could lead to lots of special case checks.  Add
    additional args to _check_auto_adjust_longer instead!!!
    """
    NO_CHANGE = 101.0
    NO_STORIES = 102.0


class Status(Enum):
    # .value used for logging:
    SUCC = 'Success'            # success
    SOFT = 'Soft error'         # soft error (more retries)
    HARD = 'Hard error'         # hard error
    TEMP = 'Temporary error'    # DNS "TRYAGAIN"
    NOUPD = 'No Update'         # don't update Feed


# system_status for working feed
SYS_WORKING = 'Working'


class Update(NamedTuple):
    """data for update_feed (returned by fetch_and_process_feed)"""
    counter: str
    status: Status
    sys_status: str
    note: Optional[str] = None
    feed_col_updates: Dict[str, Any] = {}
    # on success:
    saved: Optional[int] = None
    dup: Optional[int] = None
    skipped: Optional[int] = None
    start_delay: Optional[dt.timedelta] = None
    # on non-success:
    retry_after_min: Optional[float] = None
    randomize: bool = False     # (could now add to retry_after)


def NoUpdate(counter: str) -> Update:
    """
    update_field return value in cases
    where Field row should NOT be updated
    """
    return Update(counter, Status.NOUPD, '')


# feedparser doesn't come with type hints,
# and with the addition of sitemaps, adding
# internal, generic, typed dataclasses,
# AND lessens time format conversions.
@dataclass
class ParsedEntry:
    url: str
    guid: str | None = None
    published_dt: dt.datetime | None = None
    title: str | None = None


@dataclass
class ParsedFeed:
    entries: list[ParsedEntry]
    format: str
    feed_title: str | None
    updatefrequency: str | None
    updateperiod: str | None


# HTTP status codes to consider "soft" errors:
# yes, active feeds DO return 404 and come back to life!
HTTP_SOFT = set([404, 429])
HTTP_SOFT.update(range(500, 600))   # all 5xx (server error)

logger = logging.getLogger(__name__)  # get_task_logger(__name__)

# force logging on startup (actual logging deferred)
# see fetcher/config.py for descriptions
# please keep alphabetical:
AUTO_ADJUST_MAX_DELTA_MIN = conf.AUTO_ADJUST_MAX_DELTA_MIN
AUTO_ADJUST_MAX_DUPLICATE_PERCENT = conf.AUTO_ADJUST_MAX_DUPLICATE_PERCENT
AUTO_ADJUST_MIN_DUPLICATE_PERCENT = conf.AUTO_ADJUST_MIN_DUPLICATE_PERCENT
if AUTO_ADJUST_MIN_DUPLICATE_PERCENT >= AUTO_ADJUST_MAX_DUPLICATE_PERCENT:
    logger.error(f"AUTO_ADJUST_MIN_DUPLICATE_PERCENT ({AUTO_ADJUST_MIN_DUPLICATE_PERCENT}) >= "
                 f"AUTO_ADJUST_MAX_DUPLICATE_PERCENT ({AUTO_ADJUST_MAX_DUPLICATE_PERCENT})")

AUTO_ADJUST_MAX_POLL_MINUTES = conf.AUTO_ADJUST_MAX_POLL_MINUTES
AUTO_ADJUST_MIN_POLL_MINUTES = conf.AUTO_ADJUST_MIN_POLL_MINUTES
AUTO_ADJUST_MINUTES = conf.AUTO_ADJUST_MINUTES
AUTO_ADJUST_SMALL_DAYS = conf.AUTO_ADJUST_SMALL_DAYS
AUTO_ADJUST_SMALL_MINS = conf.AUTO_ADJUST_SMALL_MINS

DEFAULT_INTERVAL_MINS = conf.DEFAULT_INTERVAL_MINS
HTTP_CONDITIONAL_FETCH = conf.HTTP_CONDITIONAL_FETCH
MAX_FAILURES = conf.MAX_FAILURES
MAX_URL = conf.MAX_URL
MAXIMUM_BACKOFF_MINS = conf.MAXIMUM_BACKOFF_MINS
MAXIMUM_INTERVAL_MINS = conf.MAXIMUM_INTERVAL_MINS
MINIMUM_INTERVAL_MINS = conf.MINIMUM_INTERVAL_MINS
NORMALIZED_TITLE_DAYS = conf.NORMALIZED_TITLE_DAYS
RSS_FETCH_TIMEOUT_SECS = conf.RSS_FETCH_TIMEOUT_SECS
SAVE_RSS_FILES = conf.SAVE_RSS_FILES
SAVE_PARSE_ERRORS = conf.SAVE_PARSE_ERRORS
SKIP_HOME_PAGES = conf.SKIP_HOME_PAGES
UNDEAD_FEEDS = conf.UNDEAD_FEEDS
UNDEAD_FEED_MAX_DAYS = conf.UNDEAD_FEED_MAX_DAYS
VERIFY_CERTIFICATES = conf.VERIFY_CERTIFICATES

# disable SSL verification warnings w/ requests verify=False
if not VERIFY_CERTIFICATES:
    warnings.simplefilter('ignore', InsecureRequestWarning)

# RDF Site Summary 1.0 Modules: Syndication
# https://web.resource.org/rss/1.0/modules/syndication/
_DAY_MINS = 24 * 60
UPDATE_PERIODS_MINS = {
    'hourly': 60,
    'always': 60,       # treat as hourly (seen at www.baokontum.com.vn)
    'daily': _DAY_MINS,
    'dayly': _DAY_MINS,  # http://cuba.cu/feed & http://tribuna.cu/feed
    'weekly': 7 * _DAY_MINS,
    'monthly': 30 * _DAY_MINS,
    'yearly': 365 * _DAY_MINS,
}
DEFAULT_UPDATE_PERIOD = 'daily'  # specified in Syndication spec
DEFAULT_UPDATE_FREQUENCY = 1    # specified in Syndication spec


def _save_rss_files(dir: str, fname: Any, feed: Dict,
                    response: requests.Response, note: Optional[str] = None) -> None:
    """
    debugging helper method - saves two files for the feed (data & metadata)
    """
    summary = {
        'id': feed['id'],
        'url': feed['url'],
        'sources_id': feed['sources_id'],
        'status_code': response.status_code,
        'reason': response.reason,
        'rurl': response.url,
        'headers': dict(response.headers),
    }
    if note:
        summary['note'] = note

    path.check_dir(dir)
    json_filename = os.path.join(dir, f"{fname}-summary.json")
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=4)
    rss_filename = os.path.join(dir, f"{fname}-content.rss")
    with open(rss_filename, 'wb') as f:
        f.write(response.content)


def normalized_title_exists(session: SessionType,
                            normalized_title_hash: Optional[str],
                            sources_id: Optional[int]) -> bool:
    if normalized_title_hash is None or sources_id is None:
        # err on the side of keeping URLs
        return False
    earliest_date = dt.date.today() - dt.timedelta(days=NORMALIZED_TITLE_DAYS)
    # only care if matching rows exist, so doing nested EXISTS query
    with session.begin():
        return session.query(literal(True))\
                      .filter(session.query(Story)
                              .filter(Story.published_at >= earliest_date,
                                      Story.normalized_title_hash == normalized_title_hash,
                                      Story.sources_id == sources_id)
                              .exists())\
                      .scalar() is True


def normalized_url_exists(session: SessionType,
                          normalized_url: Optional[str]) -> bool:
    if normalized_url is None:
        return False
    # only care if matching rows exist, so doing nested EXISTS query
    with session.begin():
        return session.query(literal(True))\
                      .filter(session.query(Story)
                              .filter(Story.normalized_url ==
                                      normalized_url)
                              .exists())\
                      .scalar() is True


def _auto_adjust_stat(counter: str) -> None:
    """
    increment an auto-adjust status counter
    (try to only call once for a given feed/fetch)
    """
    stats = Stats.get()         # get singleton
    stats.incr('adjust', 1, labels=[('stat', counter)])


def _check_auto_adjust_longer(update: Update, feed: Feed,
                              next_min: int, dup_pct: float,
                              delta_min: float) -> int:
    """
    here to consider raising poll_minutues (too many dups)
    """
    # limit consideration of early polls, but late is ok.

    # NOTE: This may be a positive feedback loop: if polls are late
    # because "high water" is dropping, (and "ready" feeds backing
    # up), allowing ALL late polls will increase the number of times
    # poll_minutes is adjusted up, and increase the rate of decrease
    # of the "high water" mark (and increase the number of late polls,
    # which prohibits shortening poll periods.  Since the system is
    # written to avoid early polls (except when triggered), perhaps
    # this is an argument for primarily adjusting "up", and resetting
    # periods to a minimal value??
    if delta_min < -AUTO_ADJUST_MAX_DELTA_MIN:
        logger.info(f"  Feed {feed.id} {-delta_min:.1f} min early")
        _auto_adjust_stat('early')
        return next_min

    if feed.last_new_stories:
        last = feed.last_new_stories
    elif feed.created_at:
        last = feed.created_at
    else:
        # should not happen!
        _auto_adjust_stat('no_last')
        return next_min

    # adjust by smaller increment if:
    # 1. stories seen in last AUTO_ADJUST_SMALL_DAYS (AASD)
    # 2. or if no stories ever seen, feed is younger than AASD
    # 3. or just fetched some stories (should trigger case 1).
    since = dt.datetime.utcnow() - last
    logger.info(                # TEMP (lower to debug?)
        f"  Feed {feed.id} next: {next_min} m; {since.days} d; {dup_pct:.1f}% dup; delta {delta_min:.1f} m")
    if since.days <= AUTO_ADJUST_SMALL_DAYS or dup_pct < 100:
        next_min += AUTO_ADJUST_SMALL_MINS
    else:
        next_min += AUTO_ADJUST_MINUTES

    if next_min > AUTO_ADJUST_MAX_POLL_MINUTES:
        next_min = AUTO_ADJUST_MAX_POLL_MINUTES
        logger.info(
            f"  Feed {feed.id} poll_minutes clamped down to {next_min}")
        _auto_adjust_stat('max')
    elif feed.poll_minutes != next_min:
        _auto_adjust_stat('up')
        logger.info(f"  Feed {feed.id} adjust poll_minutes up to {next_min}")

    return next_min


def _check_auto_adjust_shorter(update: Update, feed: Feed,
                               next_min: int, dup_pct: float,
                               delta_min: float) -> int:
    """
    Here to increase poll rate (adjust poll_minutes down/shorter).
    due to too few duplicate (too many new stories)
    """
    # early is ok, but too late is not
    if delta_min > AUTO_ADJUST_MAX_DELTA_MIN:
        logger.info(f"  Feed {feed.id} {delta_min:.1f} min late")
        _auto_adjust_stat('late')
        return next_min

    if next_min > DEFAULT_INTERVAL_MINS:
        # here to bring long poll intervals back to earth quickly
        next_min = DEFAULT_INTERVAL_MINS
        how = ctr = 'reset'
    else:
        next_min -= AUTO_ADJUST_MINUTES
        how = 'adjust'
        ctr = 'down'

    if feed.update_minutes:
        # Saw adjustment down to two minutes for feed 6231 (denverpost
        # top news stories which advertises an update period of two
        # minutes!), so apply a lower bound!!
        minimum = max(feed.update_minutes, AUTO_ADJUST_MIN_POLL_MINUTES)
    else:
        minimum = AUTO_ADJUST_MIN_POLL_MINUTES

    if next_min < minimum:
        next_min = minimum
        logger.info(f"  Feed {feed.id} poll_minutes clamped up to {next_min}")
        _auto_adjust_stat('min')
    elif feed.poll_minutes != next_min:
        logger.info(f"  Feed {feed.id} {how} poll_minutes down to {next_min}")
        _auto_adjust_stat(ctr)

    return next_min


def _check_auto_adjust(update: Update, feed: Feed,
                       next_min: int,
                       prev_success: Optional[dt.datetime]) -> int:
    """
    Check if auto-adjust (adjustment of poll_minutes based on the
    ammount of duplicate stories returned on a successful poll) is
    needed.

    NOTE! This is distinct from "backoff" which is how the base poll
    rate is interpreted based on the number of consecutive fetch
    failures!!

    The code grew sufficently large that separate helper functions
    _check_auto_adjust_longer and _check_auto_adjust_shorter handle
    the two adjustment directions.

    Returns (possibly updated) next_min (minutes to next fetch).
    Separate function for easy exit, and to avoid clutter.
    """
    if update.status != Status.SUCC:
        # let backoff do the work
        return next_min

    # Only want to look at results after TWO successful polls IN A ROW,
    # where second poll happened close to on time (about "next_min" ago),
    # and so is representative.
    # NOTE: start_delay is system lantency (only) for current poll.
    if prev_success is None:
        return next_min

    # get timedelta since previous successful poll:
    since_prev_success = dt.datetime.utcnow() - prev_success

    # get delta in minutes from expected/current poll period
    # negative means polled early, positive means late.
    # polls tend to be one queue scan period late.
    delta_min = since_prev_success.total_seconds() / 60 - next_min

    # Original version of auto-adjust only adjusted poll rate
    # up/shorter/faster to make sure we got enough duplicates to
    # ensure that there was good duplication/overlap (no missing
    # stories) between polls, so it calculated the percentage of
    # duplicates (and not the new/added percentage), and the dup_pct
    # variable has persisted.

    if update.saved is None or update.dup is None:
        if update.counter not in ('not_mod', 'same_hash'):
            logger.info(
                f"  Feed {feed.id} unexpected counter {update.counter}")
        dup_pct = DupPct.NO_CHANGE
    else:
        total = update.saved + update.dup  # ignoring "skipped" (bad) urls
        if total > 0:
            dup_pct = 100 * update.dup / total
        else:
            dup_pct = DupPct.NO_STORIES

    if dup_pct >= AUTO_ADJUST_MAX_DUPLICATE_PERCENT:
        # too many dups: make poll period longer
        return _check_auto_adjust_longer(
            update, feed, next_min, dup_pct, delta_min)

    if dup_pct < AUTO_ADJUST_MIN_DUPLICATE_PERCENT:
        # too few dups: make poll period shorter
        return _check_auto_adjust_shorter(
            update, feed, next_min, dup_pct, delta_min)

    # no need for adjustment
    return next_min


def update_feed(session: SessionType,
                feed_id: int,
                start_time: dt.datetime,
                update: Update) -> None:
    """
    Update Feed row, inserts FeedEvent row, increments feeds counter

    * updates the Feed row
      + clearing "Feed.queued"
      + increment or clear Feed.last_fetch_failures
      + update Feed.next_fetch_attempt to reschedule
    * increment feeds stats counter

    so all policy can be centralized here.

    start_time used for fetch/processing time, last_fetch_attempt,
    Stories.created_at, FetchEvent.created_at, last_fetch_success
    """

    status = update.status               # for log, FetchEvent.Event
    system_status = update.sys_status    # for log, Feed.system_status
    note = update.note                   # for log, FetchEvent.note
    feed_col_updates = update.feed_col_updates

    # construct status_note for fetch_event entry "note"
    if note:
        if system_status == SYS_WORKING:  # or/also check status == Status.SUCC??
            status_note = note
        else:
            status_note = f"{system_status}; {note}"
    else:
        status_note = system_status

    with session.begin():
        # NOTE! locks row for atomic update of last_fetch_errors
        # (which is probably excessively paranoid).

        # Atomic increment IS possible without this, but we need to
        # make choices based on the new value, and to clear queued
        # after those choices.

        # Throwing an exception in this block is...  to say the least,
        # less than ideal, and the less and faster code here the
        # better (and there could be less, but at the cost of added
        # complexity).

        stmt = select(Feed).where(Feed.id == feed_id).with_for_update()
        f = session.scalars(stmt).one()
        if f is None:
            logger.info(f"  Feed {feed_id} not found in update_feed")
            return

        # apply additional updates first to simplify checks
        if feed_col_updates:
            for key, value in feed_col_updates.items():
                curr = getattr(f, key)
                if value != curr:
                    if key in LOG_AT_INFO:
                        lf = logger.info
                    else:
                        lf = logger.debug
                    # was !r to quote strings, but noisy w/ datetime
                    lf(f"  Feed {feed_id} updating {key} from {curr} to {value}")
                setattr(f, key, value)

        prev_success_time = f.last_fetch_success
        f.last_fetch_attempt = start_time  # match fetch_event & stories
        if status == Status.SUCC:
            f.last_fetch_success = start_time
        f.queued = False        # safe to requeue
        prev_system_status = f.system_status
        f.system_status = system_status

        # get normal feed update period in minutes, one of:
        # 0. poll_minutes field, if non-NULL
        # 1. update_minutes value being passed in to update Feed row (from RSS)
        # 2. update_minutes stored in feed row (if fetch or parse failed)
        # 3. default
        # (update_minutes is either a value from feed, or NULL)

        # On error, next_minutes is multipled by last_fetch_failures
        # (see mult variable).

        next_minutes = (f.poll_minutes or
                        f.update_minutes or
                        DEFAULT_INTERVAL_MINS)

        if status == Status.SUCC:
            event = FetchEvent.Event.FETCH_SUCCEEDED
            if f.last_fetch_failures > 0:
                # interested in seeing which errors are transient:
                logger.info(
                    f" Feed {feed_id}: clearing failures (was {f.last_fetch_failures}: {prev_system_status})")
            f.last_fetch_failures = failures = 0
            # many values come in via 'feed_col_updates'
        else:
            if status == Status.HARD:
                incr = 1.
            elif status == Status.SOFT:
                incr = SOFT_FAILURE_INCREMENT
            else:               # Status.TEMP
                incr = TEMP_FAILURE_INCREMENT
            failures = f.last_fetch_failures = f.last_fetch_failures + incr
            if failures >= MAX_FAILURES and not UNDEAD_FEEDS:
                event = FetchEvent.Event.FETCH_FAILED_DISABLED
                f.system_enabled = False  # disable feed
                next_minutes = None  # don't reschedule
                logger.warning(
                    f" Feed {feed_id}: disabled after {failures} failures")
            else:
                event = FetchEvent.Event.FETCH_FAILED
                if incr != 0:
                    logger.info(
                        f" Feed {feed_id}: upped last_fetch_failures to {failures}")

        if next_minutes is not None:  # rescheduling?  back off to be
            # check if auto-adjust needed, before backoff, or
            # retry-after, and update poll_minutes.
            next_minutes = _check_auto_adjust(
                update, f, next_minutes, prev_success_time)

            if f.poll_minutes != next_minutes:
                f.poll_minutes = next_minutes

            # kind to servers: with large intervals exponential
            # backoff (mult = N**failures) is extreme (1x, 2x, 4x, 8x)
            # so using linear backoff (1x, 2x, 3x, 4x)
            mult = failures

            # backoff result MUST NOT be less than next_minutes!!
            # so only apply multiplier when >= 1!
            if mult >= 1:
                next_minutes *= mult
                # cap interval...

                # if never killing feeds, allow larger max once a feed
                # reaches the point where it would have been disabled.
                if UNDEAD_FEEDS and failures > MAX_FAILURES:
                    max_mins = UNDEAD_FEED_MAX_DAYS * _DAY_MINS
                else:
                    max_mins = MAXIMUM_BACKOFF_MINS

                if next_minutes > max_mins:
                    next_minutes = max_mins

            if f.poll_minutes is None:
                if next_minutes < MINIMUM_INTERVAL_MINS:
                    next_minutes = MINIMUM_INTERVAL_MINS

            # Always honor HTTP Retry-After: header if longer (but log)
            # Only passed w/ non-success
            ram = update.retry_after_min
            if ram and ram > next_minutes:
                # 24 hours not uncommon; saw 317100 sec (88h!) once
                if ram > _DAY_MINS:
                    ram = _DAY_MINS  # limit to one day (log???)
                logger.info(
                    f"  Feed {feed_id} - using retry_after {ram} ({next_minutes})")
                next_minutes = ram

            if update.randomize:
                # Add random minute offset to break up clumps of 429
                # (Too Many Requests) errors.  In practice, quantized
                # into queuer loop period sized buckets.
                next_minutes += random.random() * 60

            f.next_fetch_attempt = next_dt = utc(next_minutes * 60)
            logger.info(
                f"  Feed {feed_id} rescheduled for {round(next_minutes)} min at {next_dt}")
        elif f.system_enabled:
            # only reason next_minutes should be None is if
            # system_enabled set False above.
            logger.error("  Feed {feed_id} enabled but not rescheduled!!!")

        # NOTE! created_at will match last_fetch_attempt
        # (and last_fetch_success if a success), Stories.created_at
        session.add(
            FetchEvent.from_info(
                feed_id,
                event,
                start_time,
                status_note))
        session.commit()
        session.close()
    # end "with session.begin()"


def _feed_update_period_mins(parsed_feed: ParsedFeed) -> Optional[int]:
    """
    Extract feed update period in minutes, if any from parsed feed.
    Returns None if <sy:updatePeriod> not present, or bogus in some way.
    """
    try:
        # (spec says default to 24h, but our current default is less,
        # so only process if tag present (which SHOULD manifest
        # as a string value, even if empty, in which case applying
        # the default is reasonable) and None if tag not present
        update_period = parsed_feed.updateperiod
        if update_period is None:  # tag not present
            return None

        # translate string to value: empty string (or pure whitespace)
        # is treated as DEFAULT_UPDATE_PERIOD
        update_period = update_period.strip().rstrip() or DEFAULT_UPDATE_PERIOD
        if update_period not in UPDATE_PERIODS_MINS:
            logger.warning(f"   Unknown update_period {update_period}")
            return None
        upm = int(UPDATE_PERIODS_MINS[update_period])
        # *should* get here with a value (unless DEFAULT_UPDATE_PERIOD is bad)

        # logger.debug(f" update_period {update_period} upm {upm}")

        # get divisor.  use default if not present or empty, or whitespace only
        update_frequency = parsed_feed.updatefrequency
        if update_frequency is not None:
            # translate to number: have seen 0.1 as update_frequency!
            ufn = float(update_frequency.strip() or DEFAULT_UPDATE_FREQUENCY)
            # logger.debug(f" update_frequency {update_frequency} ufn {ufn}")
            if ufn <= 0.0:
                return None     # treat as missing tags
        else:
            ufn = DEFAULT_UPDATE_FREQUENCY

        ret = round(upm / ufn)
        if ret <= 0:
            ret = DEFAULT_INTERVAL_MINS  # XXX maybe return None?
        # logger.debug(f" _feed_update_period_mins pd {update_period} fq {update_frequency} => {ret}")
        return ret
    except (AttributeError, KeyError, ValueError, TypeError, ZeroDivisionError) as exc:
        logger.info("    _feed_update_period_mins exception: %r", exc)
        # logger.exception("_feed_update_period_mins") # DEBUG
        return None


def _fetch_rss_feed(feed: Dict) -> requests.Response:
    """
    Fetch current feed document using Feed.url
    may add headers that make GET conditional (result in 304 status_code).
    Raises exceptions on errors
    """
    headers = {}  # User-Agent set by insecure_requests_session

    # 2023-01-31: some feeds give incorrect "no change" responses
    # ie; https://www.bizpacreview.com/feed
    # perhaps try to validate http_last_modified
    # (don't send headers if last_modified is more than a month old?)

    if HTTP_CONDITIONAL_FETCH:
        # if ETag (Entity-Tag) stashed, make GET conditional
        etag = feed.get('http_etag', None)
        if etag:
            # If-None-Match takes one or more etag values
            headers['If-None-Match'] = etag  # "value" or W/"value"
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

    with insecure_requests_session(MEDIA_CLOUD_USER_AGENT) as sess:
        response = sess.get(
            feed['url'],
            headers=headers,
            timeout=RSS_FETCH_TIMEOUT_SECS,
            verify=VERIFY_CERTIFICATES)
    return response


def request_exception_to_status(
        feed_id: int,
        exc: requests.exceptions.RequestException) -> Tuple[Status, str]:
    """
    decode RequestException into Status.{HARD,SOFT}
    and "system status" string.
    """
    # NOTE! system status used for counter label (so return only fixed strings to limit cardinality)
    # (probably already returns too many different strings!)

    # NOTE! return Status.SOFT if there is a chance the error is transitory, or due
    # to human/configuration error, to give a longer time for it to be
    # corrected.

    # ConnectionError subclasses:
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return Status.SOFT, "connect timeout"

    if isinstance(exc, requests.exceptions.SSLError):
        return Status.SOFT, "SSL error"

    # catch-all for ConnectionError:
    if isinstance(exc, requests.exceptions.ConnectionError):
        s = repr(exc)
        # DNS errors appear as negative errno values
        if '[Errno -' in s:
            if 'Name or service not known' in s:
                # soft: feeds DO come back after lookup failures!!
                # _COULD_ be a human DNS screw-up....
                return Status.SOFT, "unknown hostname"
            if 'Temporary failure in name resolution' in s:
                return Status.TEMP, "temporary DNS error"
            return Status.SOFT, "DNS error"
        # here with (among others):
        # [Errno 101] Network is unreachable,
        # [Errno 111] Connection refused,
        # [Errno 113] No route to host,
        # ProtocolError('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))
        # ProtocolError('Connection aborted.', OSError(107, 'Transport endpoint is not connected')))
        # ProtocolError('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
        # ReadTimeoutError("HTTPSConnectionPool(...): Read timed out.")
        return Status.SOFT, "connection error"

    # non-connection errors:
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return Status.SOFT, "read timeout"

    if isinstance(exc, requests.exceptions.TooManyRedirects):
        return Status.SOFT, "too many redirects"

    if isinstance(exc, (requests.exceptions.InvalidURL,
                        requests.exceptions.MissingSchema,
                        requests.exceptions.InvalidSchema)):
        return Status.HARD, "bad URL"

    # covers InvalidHeader (code error??)
    if isinstance(exc, ValueError):
        return Status.HARD, "bad value"

    # if this happens, it would be a local config error:
    if isinstance(exc, requests.exceptions.ProxyError):
        return Status.TEMP, "proxy error"

    # catch-alls:
    if isinstance(exc, (requests.exceptions.ChunkedEncodingError,
                        requests.exceptions.ContentDecodingError,
                        requests.exceptions.RetryError)):
        return Status.SOFT, "fetch error"

    logger.exception(f"Feed {feed_id}: unknown RequestException")
    return Status.SOFT, "unknown"


def _st2dt(tm: time.struct_time | None) -> dt.datetime | None:
    """
    Convert optional UTC struct_time (from feedparser published_parsed) to datetime.
    Called inside function called in comprehension! Avoid exceptions!!
    """
    if not isinstance(tm, time.struct_time):
        return None

    try:
        return dt.datetime(tm.tm_year, tm.tm_mon, tm.tm_mday,
                           tm.tm_hour, tm.tm_min, tm.tm_sec,
                           tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def _iso2dt(iso: str | None) -> dt.datetime | None:
    """
    parse optional ISO datetime from <news:publication_date>,
    return datetime object.
    returns None if cannot be parsed

    Called inside function called in comprehension! Avoid exceptions!!

    https://developers.google.com/search/docs/crawling-indexing/sitemaps/news-sitemap
    says:

    The article publication date in W3C format. Use either the
    "complete date" format (YYYY-MM-DD) or the "complete date plus
    hours, minutes, and seconds" format with time zone designator
    format (YYYY-MM-DDThh:mm:ssTZD). Specify the original date and
    time when the article was first published on your site. Don't
    specify the time when you added the article to your sitemap.

    Google accepts any of the following formats:

    Complete date: YYYY-MM-DD (1997-07-16)
    Complete date plus hours and minutes: YYYY-MM-DDThh:mmTZD (1997-07-16T19:20+01:00)
    Complete date plus hours, minutes, and seconds: YYYY-MM-DDThh:mm:ssTZD (1997-07-16T19:20:30+01:00)
    Complete date plus hours, minutes, seconds, and a decimal fraction of a second: YYYY-MM-DDThh:mm:ss.sTZD (1997-07-16T19:20:30.45+01:00)

    [Where "W3C format" above is a link to https://www.w3.org/TR/NOTE-datetime]
    """
    if iso is None:
        return None

    if iso.endswith("Z"):       # replace trailing Z with +00:00
        iso = iso[:-1] + "+00:00"
    try:
        # accepts ONLY yyyy-mm-dd[Thh:mm[:ss[.uuuuuu]][(+|-)hh:mm]]
        return dt.datetime.fromisoformat(iso)
    except ValueError:
        pass

    try:
        # try again, handling arbitrary digits of fractional seconds
        return dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        return None


def _strip(s: str | None) -> str | None:
    """
    Called inside function called in comprehension! Avoid exceptions!!
    """
    if s is None:
        return None
    return s.strip()


# feed parser has no hints; returns "FeedParserDict"
_FeedParserEntry = Any


def _fpe2pe(fpe: _FeedParserEntry) -> ParsedEntry:
    """
    Convert feedparser entry to ParsedEntry.
    Called from comprehension, cannot filter or raise exceptions!
    """
    return ParsedEntry(
        url=_strip(fpe.get("link")) or "",
        guid=fpe.get("guid"),
        title=_strip(fpe.get("title")),
        published_dt=_st2dt(fpe.get("published_parsed")))


def _sme2pe(sme: sitemap_parser.SitemapEntry) -> ParsedEntry:
    """
    Convert sitemap_parser.SitemapEntry (TypedDict) to ParsedEntry.
    Called from comprehension, cannot filter or raise exceptions!
    """
    return ParsedEntry(
        url=_strip(sme.get("loc")) or "",
        guid=None,
        title=_strip(sme.get("news_title")),
        published_dt=_iso2dt(sme.get("news_pub_date")))


def parse(url: str, response: requests.Response) -> ParsedFeed:
    """
    NOTE!! Any exception from this routine will be captured as a "note" for the feed
    """

    # try parsing as feed
    # NOTE! passing undecoded bytes!
    parsed_feed = feedparser.parse(response.content)

    # legacy common/src/python/mediawords/feed/parse.py
    # ignores "bozo", checks only "version"
    vers = parsed_feed.get('version', '')
    if vers:
        # here with parsed feed; convert to internal ParsedFeed
        title = updatefrequency = updateperiod = None
        try:
            pff = parsed_feed.feed
            title = pff.get("title")
            updatefrequency = pff.get("sy_updatefrequency")
            updateperiod = pff.get("sy_updateperiod")
        except AttributeError:
            pass

        return ParsedFeed(
            entries=[_fpe2pe(fpe) for fpe in parsed_feed.entries],
            format=vers,
            feed_title=title,
            updatefrequency=updatefrequency,
            updateperiod=updateperiod)

    # Try parsing as sitemap.
    # Pass decoded string.  Spec'ed to always be UTF-8.
    text = response.text
    if not text:
        raise Exception("empty")

    p = sitemap_parser.XMLSitemapParser(url, text)
    sitemap = p.sitemap()       # now tries to detect HTML
    s_type = sitemap.get("type")
    if not s_type:
        raise Exception("could not parse")
    if s_type != "urlset":
        raise Exception(s_type)  # html, sitemapindex here

    urlset = cast(sitemap_parser.Urlset, sitemap)

    # no overall header in urlset; if any article has a publication
    # name, grab that as the feed title.  NOTE! Tends to be VERY
    # short, and the same across multiple sitemaps from the same site.
    feed_title = None
    for sme in urlset["pages"]:
        pub_name = sme.get("news_pub_name")  # google <news:name>
        if pub_name:
            feed_title = f"{pub_name} Google News sitemap"
            break

    return ParsedFeed(
        entries=[_sme2pe(sme) for sme in urlset["pages"]],
        format=s_type,
        feed_title=feed_title,
        updatefrequency=None,
        updateperiod=None)


def make_story(feed_id: int,
               fetched_at: dt.datetime,
               entry: ParsedEntry) -> Story:
    s = Story()
    s.feed_id = feed_id
    s.url = url = entry.url
    s.normalized_url = urls.normalize_url(url)
    s.domain = urls.canonical_domain(url)
    s.guid = entry.guid
    s.published_at = entry.published_dt

    try:
        # code prior to this should have checked for title uniqueness biz
        # logic
        # make sure we can save it in the DB by removing NULL chars and
        # such
        s.title = util.clean_str(entry.title)
        s.normalized_title = titles.normalize_title(entry.title or "")
        s.normalized_title_hash = hashlib.md5(
            s.normalized_title.encode()).hexdigest()
    except AttributeError:
        s.title = None
        s.normalized_title = None
        s.normalized_title_hash = None
    s.fetched_at = fetched_at
    return s


def fetch_and_process_feed(
        session: SessionType, feed_id: int, now: dt.datetime) -> Update:
    """
    Was fetch_feed_content: this is THE routine called in a worker.
    Made a single routine for clarity/communication.
    """
    stats = Stats.get()         # get singleton
    with session.begin():
        # lock row for duration of (sanity-check) transaction:
        # atomically checks if timestamp from queue matches
        # f.last_fetch_attempt, and if so, updates last_fetch_attempt
        # to "now".  While this isn't an IRONCLAD guarantee of
        # exclusive access, it's a bit of added paranoia
        # (search for "tri-state" below for an alternatve).

        stmt = select(Feed).where(Feed.id == feed_id).with_for_update()
        f = session.scalars(stmt).one()
        if f is None:
            logger.warning(f"feed_worker: feed {feed_id} not found")
            return NoUpdate('missing')

        # Sanity clause, in case DB entry modified while in queue:
        # reasons for being declared insane:
        # * db entry marked inactive by human
        # * db entry disabled by fetcher
        # * db entry not marked as queued
        # * db entry next_fetch_attempt set, and in the future.

        #     Driftwood (Groucho):
        #       It's all right. That's, that's in every contract.
        #       That's, that's what they call a sanity clause.
        #     Fiorello (Chico):
        #       Ha-ha-ha-ha-ha! You can't fool me.
        #       There ain't no Sanity Clause!
        #     Marx Brothers' "Night at the Opera" (1935)

        if (not f.active
                or not f.system_enabled
                or not f.queued
                # OLD: queue_feeds w/ command line used to clear next_fetch_attempt
                # or f.next_fetch_attempt and f.next_fetch_attempt > now
            ):
            logger.info(
                f"insane: act {f.active} ena {f.system_enabled} qd {f.queued} nxt {f.next_fetch_attempt} last {f.last_fetch_attempt}")
            # tempting to clear f.queued here if set, but that
            # increases risk of the feed being queued twice.
            # instead rely on "stray feed catcher" in scripts/queue_feeds.py
            return NoUpdate('insane')

        feed = f.as_dict()      # code below expects dict
        # end with session.begin() & with_for_update

    start_delay = None
    if feed['next_fetch_attempt']:
        # delay from when ready to queue to start of processing
        start_delay = now - feed['next_fetch_attempt']
        stats.timing_td('start_delay', start_delay)

    # display sources_id for rate control monitoring
    logger.info(
        f"Feed {feed_id} srcid {feed['sources_id']}: {feed['url']} start_delay {start_delay}")

    # first thing is to fetch the content
    response = _fetch_rss_feed(feed)

    if SAVE_RSS_FILES:
        # NOTE! saves one file per SOURCE!  bug and feature?!
        _save_rss_files(path.INPUT_RSS_DIR, feed['sources_id'], feed, response)

    # BAIL: HTTP failed (not full response or "Not Changed")
    rsc = response.status_code
    if rsc != 200 and rsc != 304:
        if rsc in HTTP_SOFT:
            status = Status.SOFT
        else:
            status = Status.HARD

        reason = response.reason
        if reason:
            # include reason (in case of non-standard response code)
            sys_status = f"HTTP {rsc} {reason}"
        else:
            sys_status = f"HTTP {rsc}"

        # Testing: see how often Retry-After is set, and how (usually int sec).
        retry_after = response.headers.get('Retry-After', None)
        rretry_after = None
        if retry_after:
            logger.info(
                f"   Feed {feed_id}: Retry-After: {retry_after} w/ {sys_status}")
            try:
                # convert to (real) minutes
                rretry_after = int(retry_after) / 60
            except ValueError:
                pass

        # limiting tag cardinality, only a few, common codes for now.
        # NOTE! 429 is "too many requests"
        if rsc in (403, 404, 429):
            counter = f"http_{rsc}"
        else:
            counter = f"http_{rsc//100}xx"
        return Update(counter, status, sys_status,
                      retry_after_min=rretry_after,
                      randomize=(rsc == 429))

    # Entity Tag may be W/"value" or "value", so keep as-is
    etag = response.headers.get('ETag', None)

    # kept unparsed; just sent back with If-Modified-Since.
    lastmod = response.headers.get('Last-Modified', None)

    # NOTE!!! feed_col_updates only currently used on "success",
    # if feed processing stopped by a bug in our code, we will
    # try again with unchanged data after the bug is fixed,
    # and the feed is reenabled.

    # responded with data, or "not changed", so update last_fetch_success
    feed_col_updates: Dict[str, Any] = {}  # XXX use a Feed object????

    # https://www.rfc-editor.org/rfc/rfc9110.html#status.304
    # says a 304 response MUST have an ETag if 200 would have.
    # so always save it (even if that means NULLing it out)
    feed_col_updates['http_etag'] = etag

    # Last-Modified is not required in 304 response!
    # always save on 200 (even if that means NULLing it out)
    if response.status_code == 200 or lastmod:
        feed_col_updates['http_last_modified'] = lastmod

    # BAIL: server says file hasn't changed (no data returned)
    # treated as success
    if response.status_code == 304:
        # record if feed has ever sent 304 response.
        feed_col_updates['http_304'] = True
        return Update('not_mod', Status.SUCC, SYS_WORKING,
                      note="not modified",
                      feed_col_updates=feed_col_updates)

    # code below this point expects full body w/ RSS
    if response.status_code != 200:
        # should not get here!
        logger.error(
            f"  Feed {feed_id} - unexpected status {response.status_code}")

    # try to parse the content, parsing all the stories
    try:
        parsed_feed = parse(feed['url'], response)
        format = parsed_feed.format
        logger.debug(f"  Feed {feed_id} format {format}")
    except JobTimeoutException:
        raise
    except Exception as exc:    # RARE catch-all!
        # BAIL: couldn't parse it correctly

        if SAVE_PARSE_ERRORS:
            # NOTE! Saving per-feed
            _save_rss_files(path.PARSE_ERROR_DIR, feed['id'],
                            feed, response, note=repr(exc))
        return Update('parse_err', Status.SOFT, 'parse error',
                      note=repr(exc))

    # Moved after parse (at the cost of CPU time),
    # but means feed URLs that are replaced with HTML
    # will back off, and eventually be disabled.
    new_hash = hashlib.md5(response.content).hexdigest()
    if new_hash == feed['last_fetch_hash']:
        # BAIL: no changes since last time
        return Update('same_hash', Status.SUCC, SYS_WORKING,
                      note="same hash",
                      feed_col_updates=feed_col_updates)
    feed_col_updates['last_fetch_hash'] = new_hash

    saved, dup, skipped = save_stories_from_feed(
        session, now, feed, parsed_feed)

    # may update feed_col_updates dict (add new "name")
    check_feed_title(feed, parsed_feed, feed_col_updates)

    # see if feed indicates update period
    update_minutes = _feed_update_period_mins(parsed_feed)
    # cap update period here (rather than burden fetches_per_minute query)
    if update_minutes is not None and \
       update_minutes > MAXIMUM_INTERVAL_MINS:
        update_minutes = MAXIMUM_INTERVAL_MINS
    if feed['update_minutes'] != update_minutes:
        feed_col_updates['update_minutes'] = update_minutes

    if saved > 0:
        feed_col_updates['last_new_stories'] = now

    return Update('ok', Status.SUCC, SYS_WORKING,
                  note=f"{skipped} skipped / {dup} dup / {saved} added",
                  feed_col_updates=feed_col_updates,
                  saved=saved, dup=dup, skipped=skipped,
                  start_delay=start_delay)


def save_stories_from_feed(session: SessionType,
                           now: dt.datetime,
                           feed: Dict,  # db entry
                           parsed_feed: ParsedFeed) -> Tuple[int, int, int]:
    """
    Take parsed feed, so insert all the (valid) entries.
    returns (saved_count, dup_count, skipped_count)
    """
    stats = Stats.get()         # get singleton

    def stories_incr(status: str) -> None:
        """call exactly ONCE for each story processed"""
        stats.incr('stories', 1, labels=[('stat', status)])

    skipped_count = dup_count = saved_count = 0
    parsed_feed_url = None
    feed_url_scheme = None
    for entry in parsed_feed.entries:
        try:
            link = entry.url
            if link is None:
                logger.debug(" * skip missing URL")
                stories_incr('nourl')
                skipped_count += 1
                continue

            if not util.is_absolute_url(link):
                # skip relative URLs
                # raised logging to info to see what we're getting, and if it's
                # worth generalizing scheme handling below and getting from
                # feed.
                logger.info(
                    f" * skip relative URL: %s (feed %s)",
                    link,
                    feed['id'])
                stories_incr('relurl')
                skipped_count += 1
                continue

            # Check for if URL has scheme, if not, take from feed URL
            # (as in an HTML document).  This is rare, so parse the feed
            # URL on the fly, but save, since it's likely to happen more
            # than once within a feed document.
            # NOTE! calling count_stories here will cause double counting!!
            # normalized_url (unique key in stories table) already has http:
            if link.startswith("//"):
                if feed_url_scheme is None:
                    try:
                        # subset of urlparse, don't care about tags/queries
                        parsed_feed_url = urlsplit(link, allow_fragments=False)
                        feed_url_scheme = parsed_feed_url.scheme
                    except ValueError:
                        feed_url_scheme = ''
                if feed_url_scheme:
                    link = f"{feed_url_scheme}:{link}"
                    logger.info(
                        " * added scheme: %s (feed %s)", link, feed['id'])

            if len(link) > MAX_URL:
                logger.debug(f" * URL too long: {link}")
                stories_incr('toolong')
                skipped_count += 1
                continue

            try:
                # and skip very common homepage patterns:
                if mcmetadata.urls.is_homepage_url(link):
                    # initially skipped above test, but that exposed
                    # subsequent code paths to unexpected errors
                    if SKIP_HOME_PAGES:
                        logger.info(f" * skip homepage URL: {link}")
                        if '?' in link:
                            stories_incr('home_query')
                        else:
                            stories_incr('home')
                        skipped_count += 1
                        continue
            except (ValueError, TypeError):
                logger.debug(f" * bad URL: {link}")
                stories_incr('bad')
                skipped_count += 1
                continue

            s = make_story(feed['id'], now, entry)
            # skip urls from high-quantity non-news domains
            # we see a lot in feeds
            if mcmetadata.urls.is_non_news_domain(s.domain):
                logger.debug(f" * skip non_news_domain URL: {link}")
                stories_incr('nonews')
                skipped_count += 1
                continue
            s.sources_id = feed['sources_id']
            # only save if url is unique, and title is unique recently
            if not normalized_url_exists(session, s.normalized_url):
                if not normalized_title_exists(
                        session, s.normalized_title_hash, s.sources_id):

                    # need to commit one by one so duplicate URL keys don't stop a larger insert from happening
                    # those are *expected* errors, so we can ignore them
                    with session.begin():
                        session.add(s)
                        session.commit()
                    stories_incr('ok')
                    saved_count += 1
                else:
                    # raised to info 2022-10-27
                    logger.info(
                        f" * skip duplicate title URL: {link} | {s.normalized_title} | {s.sources_id}")
                    stories_incr('dup_title')
                    dup_count += 1
            else:
                logger.debug(
                    f" * skip duplicate normalized URL: {link} | {s.normalized_url}")
                stories_incr('dup_url')
                dup_count += 1
        except (AttributeError, KeyError, ValueError, UnicodeError) as exc:
            # NOTE!! **REALLY** easy for coding errors to end up here!!!
            # couldn't parse the entry - skip it
            logger.debug(f"Bad rss entry {link}: {exc}")

            # control via environment var for debug???
            # should be less common w/ 'nourl' and 'bad' checks.
            # PLB: want to better understand when this happens,
            # and why, and perhaps add safeguarding to code.
            # NOTE! can end up here if is_homepage_url not called!
            logger.exception(f"bad rss entry {link}")

            stories_incr('bad2')
            skipped_count += 1
        except (IntegrityError, PendingRollbackError, UniqueViolation):
            # expected exception - log and ignore
            logger.debug(
                f" * duplicate normalized URL: {s.normalized_url}")
            stories_incr('dupurl2')
            dup_count += 1

    # assert len(parsed_feed.entries) == (saved_count+dup_count+skipped_count)
    # ???
    return saved_count, dup_count, skipped_count


def check_feed_title(feed: Dict,
                     parsed_feed: ParsedFeed,
                     feed_col_updates: Dict) -> None:
    # update feed title (if it has one and it changed)
    try:
        title = parsed_feed.feed_title
        if title and len(title) > 0:
            title = ' '.join(title.split())  # condense whitespace

            if title and feed['rss_title'] != title:
                feed_col_updates['rss_title'] = title
    except AttributeError:
        # if the feed has no title that isn't really an error, just skip safely
        pass

################


def feed_worker(item: Item) -> None:
    """
    Fetch a feed, parse out stories, store them
    :param self: this maintains the single session to use for all DB operations
    :param feed_id: integer Feed id
    """

    feed_id = item.id
    start = dt.datetime.utcnow()
    try:
        # here is where the actual work is done:
        with Session() as session:
            # XXX pass prev_success
            u = fetch_and_process_feed(session, feed_id, start)
    except requests.exceptions.RequestException as exc:
        status, system_status = request_exception_to_status(feed_id, exc)
        u = Update(system_status.lower().replace(' ', '_'),
                   status, system_status,
                   note=repr(exc))
    except JobTimeoutException:
        u = Update('job_timeout', Status.SOFT, 'job timeout')
    except Exception as exc:
        # This is the ONE place that catches ALL fetch exceptions;
        # log the backtrace so the problem can be fixed, and requeue
        # the job.

        logger.exception("feed_worker")
        u = Update('exception', Status.SOFT, 'caught exception',
                   note=repr(exc))

    set_job_timeout()           # clear timeout alarm
    # fetch + processing time:
    total_td = dt.datetime.utcnow() - start
    total_sec = total_td.total_seconds()

    # maybe vary message severity based on status??
    logger.info(
        f"  Feed {feed_id} {u.status.value} in {total_sec:.03f} sec: {u.sys_status}; {u.note or ''}")

    stats = Stats.get()         # get stats client singleton object
    stats.incr('feeds', 1, labels=[('stat', u.counter)])

    # total time is multi-modal (connection timeouts), so split by status.
    # NOTE! stats.timers.mc.prod.rss-fetcher.total.status_SUCC.count
    # is a count of all successful fetches.
    stats.timing('total', total_sec,
                 labels=[('status', u.status.name)])

    if u.status != Status.NOUPD:
        with Session() as session:
            update_feed(session, feed_id, start, u)

        # if repeated Status.TEMP errors seen, sleep here??
        # (to avoid spinning through feeds incrementing failures)
