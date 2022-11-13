"""
Code for tasks run in worker processes.

NOTE!! Great effort has been made to avoid catching all
(Base)Exception all over the place because queued tasks can be
interrupted by a fetcher.queue.JobTimeoutException, and rq also
handles SystemExit exceptions for orderly (warm) shutdown.
"""

import datetime as dt
from enum import Enum
import hashlib
import json
from typing import Any, Dict, NamedTuple, Optional, Tuple
import logging
import logging.handlers
import os
import random
import time
import warnings

# PyPI
import feedparser
import mcmetadata.urls
from psycopg2.errors import UniqueViolation
import requests
import requests.exceptions
# NOTE! All references to rq belong in queue.py!
from setproctitle import setproctitle
from sqlalchemy import literal
from sqlalchemy.exc import (    # type: ignore[attr-defined]
    IntegrityError, PendingRollbackError)
from sqlalchemy.sql.expression import case
import sqlalchemy.sql.functions as func  # avoid overriding "sum"
from urllib3.exceptions import InsecureRequestWarning

# feed fetcher:
from fetcher import APP, DYNO
from fetcher.config import conf
from fetcher.database import Session, SessionType
from fetcher.database.functions import greatest
from fetcher.database.models import Feed, FetchEvent, Story, utc
import fetcher.path as path
import fetcher.queue
from fetcher.stats import Stats
import fetcher.queue
import fetcher.util as util


# set of field_col_changes fields to log at info (else log at debug)
LOG_AT_INFO = {'update_minutes', 'name'}


# take twice as many soft failures to disable feed
# to lessen spurrious disabling due to transient/human errors.
SOFT_FAILURE_INCREMENT = 0.5


class Status(Enum):
    # .value used for logging:
    SUCC = 'Success'            # success
    SOFT = 'Soft error'         # soft error (never disable)
    HARD = 'Hard error'         # hard error
    NOUPD = 'No Update'         # don't update Feed


class Update(NamedTuple):
    """data for update_feed (returned by fetch_and_process_feed)"""
    counter: str
    status: Status
    sys_status: str
    note: Optional[str] = None
    feed_col_updates: Dict[str, Any] = {}


def NoUpdate(counter: str) -> Update:
    """
    update_field return value in cases
    where Field row should NOT be updated
    """
    return Update(counter, Status.NOUPD, '')


# HTTP status codes to consider "soft" errors:
HTTP_SOFT = set([429, 500, 502, 503])

# force logging on startup (actual logging deferred)
# please keep alphabetical:
NORMALIZED_TITLE_DAYS = conf.NORMALIZED_TITLE_DAYS
DEFAULT_INTERVAL_MINS = conf.DEFAULT_INTERVAL_MINS
MAX_FAILURES = conf.MAX_FAILURES
MINIMUM_INTERVAL_MINS = conf.MINIMUM_INTERVAL_MINS
MINIMUM_INTERVAL_MINS_304 = conf.MINIMUM_INTERVAL_MINS_304
RSS_FETCH_TIMEOUT_SECS = conf.RSS_FETCH_TIMEOUT_SECS
SAVE_RSS_FILES = conf.SAVE_RSS_FILES
VERIFY_CERTIFICATES = conf.VERIFY_CERTIFICATES

logger = logging.getLogger(__name__)  # get_task_logger(__name__)

# disable SSL verification warnings w/ requests verify=False
if not VERIFY_CERTIFICATES:
    warnings.simplefilter('ignore', InsecureRequestWarning)

# mediacloud/backend/apps/common/src/python/mediawords/util/web/user_agent/__init__.py has
#    # HTTP "From:" header
#    __OWNER = 'info@mediacloud.org'
#
#    # HTTP "User-Agent:" header
#    __USER_AGENT = 'mediacloud bot for open academic research (http://mediacloud.org)'
# see https://www.rfc-editor.org/rfc/rfc9110.html#section-10.1.2
# with regard to From: header
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'

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


def _save_rss_files(feed: Dict, response: requests.Response) -> None:
    """
    debugging helper method - saves two files for the feed to paths.
    only saves one feed per source? bug and feature!
    """
    srcid = feed['sources_id']
    summary = {
        'id': feed['id'],
        'url': feed['url'],
        'sourcesId': srcid,
        'statusCode': response.status_code,
        'headers': dict(response.headers),
    }

    path.check_dir(path.INPUT_RSS_DIR)
    json_filename = os.path.join(path.INPUT_RSS_DIR, f"{srcid}-summary.json")
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=4)
    rss_filename = os.path.join(path.INPUT_RSS_DIR, f"{srcid}-content.rss")
    with open(rss_filename, 'w', encoding='utf-8') as f:
        f.write(response.text)


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


# used by scripts/queue_feeds.py, but moved here
# because needs to be kept in sync with queuing policy
# in update_feed().

# NOTE! This returns a maximal value
# (without trying to account for backoff due to errors).
def fetches_per_minute(session: SessionType) -> float:
    """
    Return average expected fetches per minute, based on
    Feed.update_minutes (derived from <sy:updatePeriod> and
    <sy:updateFrequency>).

    NOTE!! This needs to be kept in sync with the policy in
    update_feed() (below)
    """
    q = Feed._active_filter(
        session.query(
            func.sum(
                1.0 /
                # never faster than minimum interval
                # (but allow lower minimum if server sends HTTP 304)
                greatest(
                    # use DEFAULT_INTERVAL_MINS if update_minutes is NULL
                    func.coalesce(
                        Feed.update_minutes,
                        DEFAULT_INTERVAL_MINS),
                    case([(Feed.http_304, MINIMUM_INTERVAL_MINS_304)],
                         else_=MINIMUM_INTERVAL_MINS)
                )  # greatest
            )  # sum
        )  # query
    )  # active
    return q.one()[0] or 0  # handle empty db!


# start_time used for fetch/processing time, last_fetch_attempt,
# Stories.created_at, FetchEvent.created_at, last_fetch_success
def update_feed(session: SessionType,
                feed_id: int,
                start_time: dt.datetime,
                update: Update) -> None:
    """
    Update Feed row, inserts FeedEvent row, increments feeds counter

    * updates the Feed row
      + clearing "Feed.queued"
      + increment or clear Feed.last_fetch_failures
      + update Feed.next_fetch_attempt (or not) to reschedule
    * increment feeds stats counter

    so all policy can be centralized here.

    ***NOTE!!*** Any changes here in requeue policy
    need to be reflected in fetches_per_minite (above)
    """

    status = update.status               # for log, FetchEvent.Event
    system_status = update.sys_status    # for log, Feed.system_status
    note = update.note                   # for log, FetchEvent.note
    feed_col_updates = update.feed_col_updates

    # fetch_event entry (just add system_status to fetch_event?)
    if note:
        if system_status == "Working":  # also check status == Status.SUCC??
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

        f = session.get(        # type: ignore[attr-defined]
            Feed, feed_id, with_for_update=True)
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
                    # !r (repr) to quote strings
                    lf(f"  Feed {feed_id} updating {key} from {curr!r} to {value!r}")
                setattr(f, key, value)

        f.last_fetch_attempt = start_time  # match fetch_event & stories
        if status == Status.SUCC:
            f.last_fetch_success = start_time
        f.queued = False        # safe to requeue
        prev_system_status = f.system_status
        f.system_status = system_status

        # get normal feed update period in minutes, one of:
        # 1. new value being passed in to update Feed row (from RSS)
        # 2. value currently stored in feed row (if fetch or parse failed)
        # 3. default
        # (update_minutes is either a value from feed, or NULL)
        next_minutes = f.update_minutes or DEFAULT_INTERVAL_MINS

        if status == Status.SUCC:
            event = FetchEvent.Event.FETCH_SUCCEEDED
            f.last_fetch_failures = 0
            # many values come in via 'feed_col_updates'
        else:
            if status == Status.HARD:
                incr = 1.
            else:
                incr = SOFT_FAILURE_INCREMENT
            failures = f.last_fetch_failures = f.last_fetch_failures + incr
            if failures >= MAX_FAILURES:
                event = FetchEvent.Event.FETCH_FAILED_DISABLED
                f.system_enabled = False  # disable feed
                next_minutes = None  # don't reschedule
                logger.warning(
                    f" Feed {feed_id}: disabled after {failures} failures")
            else:
                event = FetchEvent.Event.FETCH_FAILED
                logger.info(
                    f" Feed {feed_id}: upped last_fetch_failures to {failures}")

            if next_minutes is not None:
                if failures > 0:
                    # back off to be kind to servers:
                    # with large intervals exponential backoff is extreme
                    # (12h, 1d, 2d, 4d), so using linear backoff
                    next_minutes *= int(failures + 0.5)

                if status == Status.SOFT:
                    # Add random minute offset to break up clumps of 429
                    # (Too Many Requests) errors:
                    next_minutes += random.random() * 60

        if next_minutes is not None:  # reschedule?
            # clamp interval to a minimum value

            # Allow different (shorter) interval if server sends
            # HTTP 304 Not Modified (no data transferred if ETag
            # or Last-Modified not changed).  Initial observation
            # is that 304's are most common on feeds that
            # advertise a one hour update interval!

            # NOTE!! logic here is replicated (in an SQL query)
            # in fetches_per_minite() function above, and any
            # changes need to be reflected there as well!!!

            if f.http_304:
                if next_minutes < MINIMUM_INTERVAL_MINS_304:
                    next_minutes = MINIMUM_INTERVAL_MINS_304
            else:
                if next_minutes < MINIMUM_INTERVAL_MINS:
                    next_minutes = MINIMUM_INTERVAL_MINS

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


def _feed_update_period_mins(   # type: ignore[no-any-unimported]
        parsed_feed: feedparser.FeedParserDict) -> Optional[int]:
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

        ret = round(upm / ufn)
        if ret <= 0:
            ret = DEFAULT_INTERVAL_MINS  # XXX maybe return None?
        #logger.debug(f" _feed_update_period_mins pd {update_period} fq {update_frequency} => {ret}")
        return ret
    except (KeyError, ValueError, TypeError, ZeroDivisionError) as exc:
        logger.info(f"    _feed_update_period_mins exception: {exc}")
        # logger.exception("_feed_update_period_mins") # DEBUG
        return None


def _fetch_rss_feed(feed: Dict) -> requests.Response:
    """
    Fetch current feed document using Feed.url
    may add headers that make GET conditional (result in 304 status_code).
    Raises exceptions on errors
    """
    headers = {'User-Agent': USER_AGENT}

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

    response = requests.get(
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
        if 'Name or service not known' in s:
            # _COULD_ be a human DNS screw-up....
            return Status.HARD, "unknown hostname"
        # DNS errors appear as negative errno values
        if '[Errno -' in s:
            return Status.SOFT, "DNS error"
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
        return Status.SOFT, "proxy error"

    # catch-alls:
    if isinstance(exc, (requests.exceptions.ChunkedEncodingError,
                        requests.exceptions.ContentDecodingError,
                        requests.exceptions.RetryError)):
        return Status.SOFT, "fetch error"

    logger.exception(f"Feed {feed_id}: unknown RequestException")
    return Status.SOFT, "unknown"


def fetch_and_process_feed(
        session: SessionType, feed_id: int, now: dt.datetime, queue_ts_iso: str) -> Update:
    """
    Was fetch_feed_content: this is THE routine called in a worker.
    Made a single routine for clarity/communication.
    """

    try:
        qtime = dt.datetime.fromisoformat(queue_ts_iso)
        stats = Stats.get()     # get singleton
        stats.timing_td('time_in_queue', now - qtime)
    except (ValueError, TypeError) as e:
        # not important enough to log w/o rate limiting
        qtime = None

    with session.begin():
        # lock row for duration of (sanity-check) transaction:
        # atomically checks if timestamp from queue matches
        # f.last_fetch_attempt, and if so, updates last_fetch_attempt
        # to "now".  While this isn't an IRONCLAD guarantee of
        # exclusive access, it's a bit of added paranoia
        # (search for "tri-state" below for an alternatve).

        f = session.get(        # type: ignore[attr-defined]
            Feed, feed_id, with_for_update=True)
        if f is None:
            logger.warning(f"feed_worker: feed {feed_id} not found")
            return NoUpdate('missing')

        # Sanity clause, in case DB entry modified while in queue:
        # reasons for being declared insane:
        # * db entry marked inactive by human
        # * db entry disabled by fetcher
        # * db entry not marked as queued
        # * db entry last_fetch_attempt does not match queue entry
        #       (depends on isoformat/fromisoformat fidelity,
        #        and matching DB dt granularity. rq allows passing
        #        of datetime (uses pickle rather than json)
        #        if deemed necessary, but logging is ugly).
        # * db entry next_fetch_attempt set, and in the future.

        #     Driftwood (Groucho):
        #       It's all right. That's, that's in every contract.
        #       That's, that's what they call a sanity clause.
        #     Fiorello (Chico):
        #       Ha-ha-ha-ha-ha! You can't fool me.
        #       There ain't no Sanity Clause!
        #     Marx Brothers' "Night at the Opera" (1935)

        if (not f.active or
            not f.system_enabled or
            not f.queued or
            (qtime and f.last_fetch_attempt != qtime) or
                (f.next_fetch_attempt and f.next_fetch_attempt > now)):
            logger.info(
                f"insane: act {f.active} ena {f.system_enabled} qd {f.queued} nxt {f.next_fetch_attempt} last {f.last_fetch_attempt} qt {qtime}")
            # tempting to clear f.queued here if set, but that
            # increases risk of the queue being queued twice
            # instead rely on "stray feed catcher" in scripts/queue_feeds.py
            return NoUpdate('insane')

        # mark time of actual attempt (start)
        # above `f.last_fetch_attempt != qtime` depends on this
        # (could also replace "queued" with a tri-state: IDLE, QUEUED, ACTIVE):
        f.last_fetch_attempt = now
        feed = f.as_dict()      # code below expects dict
        session.commit()
        # end with session.begin() & with_for_update

    start_delay = None
    if feed['next_fetch_attempt']:
        # delay from when ready to queue to start of processing
        start_delay = now - feed['next_fetch_attempt']
        stats.timing_td('start_delay', start_delay)

    logger.info(
        f"Working on feed {feed_id}: {feed['url']} start_delay {start_delay}")

    # first thing is to fetch the content
    response = _fetch_rss_feed(feed)

    if SAVE_RSS_FILES:
        _save_rss_files(feed, response)

    # BAIL: HTTP failed (not full response or "Not Changed")
    rsc = response.status_code
    if rsc != 200 and rsc != 304:
        if rsc in HTTP_SOFT:
            status = Status.SOFT
        else:
            status = Status.HARD

        rurl = response.url
        reason = response.reason
        if reason:
            # include reason (in case of non-standard response code)
            sys_status = f"HTTP {rsc} {reason}"
        else:
            sys_status = f"HTTP {rsc}"

        # Testing: see how often Retry-After is set, and how.
        retry_after = response.headers.get('Retry-After', None)
        if retry_after:
            logger.info(
                f"   Feed {feed_id}: Retry-After: {retry_after} w/ {sys_status}")

        # limiting tag cardinality, only a few, common codes for now.
        # NOTE! 429 is "too many requests"
        if rsc in (403, 404, 429):
            counter = f"http_{rsc}"
        else:
            counter = f"http_{rsc//100}xx"
        return Update(counter, status, sys_status)

    # NOTE! 304 response will not have a body (terminated by end of headers)
    # so the last hash isn't (over)written below
    # (tho presumably if we get 304 responses, the next feed we get
    # will be different).
    new_hash = hashlib.md5(response.content).hexdigest()

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
        return Update('not_mod', Status.SUCC, "not modified",
                      feed_col_updates=feed_col_updates)

    # code below this point expects full body w/ RSS
    if response.status_code != 200:
        # should not get here!
        logger.error(
            f"  Feed {feed_id} - unexpected status {response.status_code}")

    # BAIL: no changes since last time
    # treated as success
    if new_hash == feed['last_fetch_hash']:
        if feed['http_304']:
            # considering setting http_304 to 'f'
            # (disabling faster fetching when both "no change" and "same hash" occur)
            logger.info(f"   Feed {feed_id} same hash w/ http_304 set")
        return Update('same_hash', Status.SUCC, "same hash",
                      feed_col_updates=feed_col_updates)

    feed_col_updates['last_fetch_hash'] = new_hash

    # try to parse the content, parsing all the stories
    try:
        parsed_feed = feedparser.parse(response.text)
        if parsed_feed.bozo:
            # BAIL: couldn't parse it correctly
            return Update('parse_err', Status.SOFT, 'parse error',
                          note=repr(parsed_feed.bozo_exception))
    except UnicodeError as exc:
        # w/ feedparser 6.0.10:
        # feedparser/mixin.py", line 359, in handle_charref:
        # text = chr(c).encode('utf-8')
        # UnicodeEncodeError: 'utf-8' codec can't encode character '\ud83d' in
        # position 0: surrogates not allowed
        return Update('unicode', Status.SOFT, 'unicode error',
                      note=repr(exc))

    saved, skipped = save_stories_from_feed(session, now, feed, parsed_feed)

    # may update feed_col_updates dict (add new "name")
    check_feed_title(feed, parsed_feed, feed_col_updates)

    # see if feed indicates update period
    update_minutes = _feed_update_period_mins(parsed_feed)
    if feed['update_minutes'] != update_minutes:
        feed_col_updates['update_minutes'] = update_minutes

    return Update('ok', Status.SUCC, 'Working',
                  note=f"{skipped} skipped / {saved} added",
                  feed_col_updates=feed_col_updates)


def save_stories_from_feed(session: SessionType,  # type: ignore[no-any-unimported]
                           now: dt.datetime,
                           feed: Dict,
                           parsed_feed: feedparser.FeedParserDict) -> Tuple[int, int]:
    """
    Take parsed feed, so insert all the (valid) entries.
    returns (saved_count, skipped_count)
    """
    stats = Stats.get()         # get singleton

    def stories_incr(status: str) -> None:
        """call exactly ONCE for each story processed"""
        stats.incr('stories', 1, labels=[('stat', status)])

    skipped_count = 0
    for entry in parsed_feed.entries:
        try:
            link = getattr(entry, 'link', None)
            if link is None:
                logger.debug(" * skip missing URL")
                stories_incr('nourl')
                skipped_count += 1
                continue
            if not util.is_absolute_url(link):  # skip relative URLs
                logger.debug(f" * skip relative URL: {link}")
                stories_incr('relurl')
                skipped_count += 1
                continue

            try:
                # and skip very common homepage patterns:
                if mcmetadata.urls.is_homepage_url(link):
                    # raised to info 2022-10-27
                    logger.info(f" * skip homepage URL: {link}")
                    if '?' in link:  # added 2022-11-04
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

            s = Story.from_rss_entry(feed['id'], now, entry)
            # skip urls from high-quantity non-news domains
            # we see a lot in feeds
            if s.domain in mcmetadata.urls.NON_NEWS_DOMAINS:
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
                else:
                    # raised to info 2022-10-27
                    logger.info(
                        f" * skip duplicate title URL: {link} | {s.normalized_title} | {s.sources_id}")
                    stories_incr('dup_title')
                    skipped_count += 1
            else:
                logger.debug(
                    f" * skip duplicate normalized URL: {link} | {s.normalized_url}")
                stories_incr('dup_url')
                skipped_count += 1
        except (AttributeError, KeyError, ValueError, UnicodeError) as exc:
            # NOTE!! **REALLY** easy for coding errors to end up here!!!
            # couldn't parse the entry - skip it
            logger.debug(f"Bad rss entry {link}: {exc}")

            # control via environment var for debug???
            # should be less common w/ 'nourl' and 'bad' checks.
            # PLB: want to better understand when this happens,
            # and why, and perhaps add safeguarding to code.
            logger.exception(f"bad rss entry {link}")

            stories_incr('bad2')
            skipped_count += 1
        except (IntegrityError, PendingRollbackError, UniqueViolation) as _:
            # expected exception - log and ignore
            logger.debug(
                f" * duplicate normalized URL: {s.normalized_url}")
            stories_incr('dupurl2')
            skipped_count += 1

    entries = len(parsed_feed.entries)
    saved_count = entries - skipped_count
    return saved_count, skipped_count


def check_feed_title(feed: Dict,  # type: ignore[no-any-unimported]
                     parsed_feed: feedparser.FeedParserDict,
                     feed_col_updates: Dict) -> None:
    # update feed title (if it has one and it changed)
    try:
        title = parsed_feed.feed.title
        if len(title) > 0:
            title = ' '.join(title.split())  # condense whitespace

            if title and feed['name'] != title:
                feed_col_updates['name'] = title
    except AttributeError:
        # if the feed has no title that isn't really an error, just skip safely
        pass

################


def feed_worker(feed_id: int, ts_iso: str) -> None:
    """
    called via rq:

    MUST be run from rq SimpleWorker to achieve session caching!!!!

    Fetch a feed, parse out stories, store them
    :param self: this maintains the single session to use for all DB operations
    :param feed_id: integer Feed id
    :param ts_iso: str datetime.isoformat of time queued (Feed.last_fetch_attempt)
    """

    setproctitle(f"{APP} {DYNO} feed {feed_id}")
    start = dt.datetime.utcnow()
    try:
        # here is where the actual work is done:
        with Session() as session:
            u = fetch_and_process_feed(session, feed_id, start, ts_iso)
    except requests.exceptions.RequestException as exc:
        status, system_status = request_exception_to_status(feed_id, exc)
        u = Update(system_status.lower().replace(' ', '_'),
                   status, system_status,
                   note=repr(exc))
    except fetcher.queue.JobTimeoutException:
        u = Update('job_timeout', Status.SOFT, 'job timeout')
    except Exception as exc:
        # This is the ONE place that catches ALL exceptions;
        # log the backtrace so the problem can be fixed, and requeue
        # the job.

        logger.exception("feed_worker")
        u = Update('exception', Status.SOFT, 'caught exception',
                   note=repr(exc))

    fetcher.queue.cancel_job_timeout()
    # fetch + processing time:
    total_td = dt.datetime.utcnow() - start
    total_sec = total_td.total_seconds()

    # maybe vary message severity based on status??
    logger.info(
        f"  Feed {feed_id} {u.status.value} in {total_sec:.03f} sec: {u.sys_status}; {u.note or ''}")

    stats = Stats.get()         # get stats client singleton object
    stats.incr('feeds', 1, labels=[('stat', u.counter)])

    # total time is multi-modal (connection timeouts), so split by status.
    # UGH: started w/ upper case (.name, not .value)
    # NOTE! stats.timers.mc.prod.rss-fetcher.total.status_SUCCESS.count
    # is a count of all successful fetches.
    stats.timing('total', total_sec,
                 labels=[('status', u.status.name)])

    if u.status != Status.NOUPD:
        with Session() as session:
            update_feed(session, feed_id, start, u)
