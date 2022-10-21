# PLB ISSUES to be resolved:
# search for PLB!
# any times NOT to increment failure count??

# PLB: cleanup WISHES
# type hints for session objects
# type hints for void (-> None) functions
# create NewType for feeds_id?

import datetime as dt
from enum import Enum
import hashlib
import json
from typing import Any, Dict, Optional, Tuple
import logging
import logging.handlers
import os
import random
import time

# PyPI
import feedparser
import mcmetadata.urls
from psycopg2.errors import UniqueViolation
import requests
from setproctitle import setproctitle
from sqlalchemy import literal
from sqlalchemy.exc import IntegrityError, PendingRollbackError

# feed fetcher:
from fetcher import APP, DYNO
from fetcher.config import conf
from fetcher.database import Session, SessionType
import fetcher.database.models as models
import fetcher.path as path
from fetcher.stats import Stats
import fetcher.queue
import fetcher.util as util


class Status(Enum):
    SUCC = 'succ'               # success
    SOFT = 'soft'               # soft error (never disable)
    HARD = 'hard'               # hard error


HTTP_SOFT = set([403, 429])     # http status codes to consider "soft"

# force logging on startup (actual logging deferred)
DAY_WINDOW = conf.DAY_WINDOW
DEFAULT_INTERVAL_MINS = conf.DEFAULT_INTERVAL_MINS
MINIMUM_INTERVAL_MINS = conf.MINIMUM_INTERVAL_MINS
RSS_FETCH_TIMEOUT_SECS = conf.RSS_FETCH_TIMEOUT_SECS
SAVE_RSS_FILES = conf.SAVE_RSS_FILES

logger = logging.getLogger(__name__)  # get_task_logger(__name__)


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
    'daily': _DAY_MINS,
    'dayly': _DAY_MINS,  # http://cuba.cu/feed & http://tribuna.cu/feed
    'weekly': 7 * _DAY_MINS,
    'monthly': 30 * _DAY_MINS,
    'yearly': 365 * _DAY_MINS,
}
DEFAULT_UPDATE_PERIOD = 'daily'  # specified in Syndication spec
DEFAULT_UPDATE_FREQUENCY = 1    # specified in Syndication spec


def open_log_file() -> None:
    """
    Was once inline (not in function).

    Called from scripts/worker.py so that scripts/queue_feeds.py
    (which includes this file so it can queue a reference to feed_worker)
    doesn't create an empty tasks-fetcher.1.log file

    Maybe make a generic function for this
    (move to logargparse for use from cmd line)?
    """
    # why special format? there should be no thread action.
    logFormatter = logging.Formatter(
        "[%(levelname)s %(threadName)s] - %(asctime)s - %(name)s - : %(message)s")
    path.check_dir(path.LOG_DIR)

    # rotate file after midnight (UTC), keep 7 old files
    fileHandler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(path.LOG_DIR, f"tasks-{DYNO}.log"),
        when='midnight', utc=True, backupCount=7)
    fileHandler.setFormatter(logFormatter)
    logger.addHandler(fileHandler)


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
    earliest_date = dt.date.today() - dt.timedelta(days=DAY_WINDOW)
    # only care if matching rows exist, so doing nested EXISTS query
    with session.begin():
        return session.query(literal(True))\
                      .filter(session.query(models.Story)
                              .filter(models.Story.published_at >= earliest_date,
                                      models.Story.normalized_title_hash == normalized_title_hash,
                                      models.Story.sources_id == sources_id)
                              .exists())\
                      .scalar() is True


def normalized_url_exists(session: SessionType,
                          normalized_url: Optional[str]) -> bool:
    if normalized_url is None:
        return False
    # only care if matching rows exist, so doing nested EXISTS query
    with session.begin():
        return session.query(literal(True))\
                      .filter(session.query(models.Story)
                              .filter(models.Story.normalized_url ==
                                      normalized_url)
                              .exists())\
                      .scalar() is True


def update_feed(session: SessionType,
                feed_id: int,
                status: Status,
                note: str,
                now: dt.datetime,
                feed_col_updates: Optional[Dict] = None) -> None:
    """
    Update Feed row and insert FeedEvent row

    MUST be called from all feed_worker code paths
    (for valud queue entrues) in order to clear "queued"
    and update "next_fetch_attempt"!!!

    Trying to make this the one place that updates the Feed row,
    so all policy can be centralized here.
    """
    logger.debug(f"  Feed {feed_id} {status.name} {note}")
    try:
        total_td = dt.datetime.utcnow() - now  # fetch + processing
        total_sec = total_td.total_seconds()
        logger.debug(f"  Feed {feed_id} fetch/processing {total_sec:.06f} sec")
        stats = Stats.get()
        if stats:
            # likely to be multi-modal (connection timeouts)
            stats.timing('total', total_sec,
                         labels=[('status', status.name)])
    except BaseException as e:
        logger.debug(f"total time: {e}")

    # PLB log w/note?? (would duplicate existing logging)
    with session.begin():
        # NOTE! locks row, so atomic update of last_fetch_errors.
        # Atomic increment IS possible without this,
        # but we need to make choices based on the new value,
        # and to clear queued after those choices.
        f = session.get(models.Feed, feed_id, with_for_update=True)
        if f is None:
            logger.info(f"  Feed {feed_id} not found in update_feed")
            return

        # apply additional updates first to simplify checks
        if feed_col_updates:
            for key, value in feed_col_updates.items():
                setattr(f, key, value)

        f.last_fetch_attempt = now  # match fetch_event & stories
        f.queued = False        # safe to requeue

        # get normal feed update period in minutes, one of:
        # 1. new value being passed in to update Feed row (from RSS)
        # 2. value currently stored in feed row (if fetch or parse failed)
        # 3. default
        # (update_minutes is either a value from feed, or NULL)
        next_minutes = f.update_minutes or DEFAULT_INTERVAL_MINS

        if status == Status.SUCC:
            event = models.FetchEvent.Event.FETCH_SUCCEEDED
            f.last_fetch_failures = 0
            # many values come in via 'feed_col_updates'
            # PLB: save "working" as system_status??
        else:
            event = models.FetchEvent.Event.FETCH_FAILED
            failures = f.last_fetch_failures
            if status == Status.HARD:
                failures = f.last_fetch_failures = f.last_fetch_failures + 1
                if failures >= conf.MAX_FAILURES:
                    event = models.FetchEvent.Event.FETCH_FAILED_DISABLED
                    f.system_enabled = False
                    next_minutes = None  # don't reschedule
                    logger.warning(
                        f" Feed {feed_id}: disabled after {failures} failures")
                    # PLB: save "disabled" as system_status????
                else:
                    logger.info(
                        f" Feed {feed_id}: upped last_fetch_failures to {failures}")

            if next_minutes is not None and failures > 0:
                # back off to be kind to servers:
                # linear backoff (ie; 12h, 1d, 1.5d, 2d)
                next_minutes *= failures

                # exponential backoff:
                # kinder, but excessive delays with long initial period.
                # (ie; 12h, 1d, 2d, 4d)
                #next_minutes *= 2 ** (failures - 1)

                # add random minute offset to break up clumps
                # of 429 (Too Many Requests) errors
                next_minutes += random.random() * 60

        # PLB: save note as f.system_status??
        # (split w/ " / " and/or ":" and save front part)???
        # or pass note in two halves: system_status & detail????

        if next_minutes is not None:  # reschedule?
            if next_minutes < conf.MINIMUM_INTERVAL_MINS:
                next_minutes = conf.MINIMUM_INTERVAL_MINS  # clamp to minimum
            f.next_fetch_attempt = next_dt = models.utc(next_minutes * 60)
            logger.debug(f"  Feed {feed_id} rescheduled for {next_dt}")
        elif f.system_enabled:
            logger.error("  Feed {feed_id} enabled but not rescheduled!!!")

        # NOTE! created_at will match last_fetch_attempt
        # (and last_fetch_success if a success)
        session.add(models.FetchEvent.from_info(feed_id, event, now, note))
        session.commit()
        session.close()
    # end "with session.begin()"


def _feed_update_period_mins(
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
            ret = DEFAULT_INTERVAL_MINS
        #logger.debug(f" _feed_update_period_mins pd {update_period} fq {update_frequency} => {ret}")
        return ret
    except BaseException:
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
        timeout=RSS_FETCH_TIMEOUT_SECS)
    return response


def fetch_and_process_feed(
        session: SessionType, feed_id: int, ts_iso: str) -> None:
    """
    Was fetch_feed_content: this is THE routine called in a worker.
    Made a single routine for clarity/communication.
    ALL exits from this function should call `update_feed`
    * clear "Feed.queued"
    * create FetchEvent row
    * increment or clear Feed.last_fetch_failures
    * update Feed.next_fetch_attempt (or not) to reschedule
    """

    stats = Stats.get()         # get stats client object

    def feeds_incr(status: str) -> None:
        """
        call EXACTLY ONCE for each feed processed
        (sum of all counters should be number of feeds processed,
        can be displayed as a "stacked" graph)
        """
        stats.incr('feeds', 1, labels=[('stat', status)])

    # used in Feed.last_fetch_success, Story.fetched_at
    now = dt.datetime.utcnow()

    try:
        qtime = dt.datetime.fromisoformat(ts_iso)
        stats.timing_td('time_in_queue', now - qtime)
    except BaseException as e:
        # not important enough to log w/o rate limiting
        qtime = None

    with session.begin():
        # lock row for duration of transaction:
        f = session.get(models.Feed, feed_id, with_for_update=True)
        if f is None:
            feeds_incr('missing')
            logger.info(f"feed_worker: feed {feed_id} not found")
            return

        # Sanity clause, in case DB entry modified while in queue:
        # (including being queued more than once).
        #     Driftwood (Groucho):
        #       It's all right. That's, that's in every contract.
        #       That's, that's what they call a sanity clause.
        #     Fiorello (Chico):
        #       Ha-ha-ha-ha-ha! You can't fool me.
        #       There ain't no Sanity Clause!
        #     Marx Brothers' "Night at the Opera" (1935)

        # reasons for being declared insane:
        # * db entry marked inactive by human
        # * db entry disabled by fetcher
        # * db entry not marked as queued
        # * db entry last_fetch_attempt does not match queue entry
        #       (depends on isoformat/fromisoformat fidelity,
        #        and matching DB dt granularity. rq allows passing
        #        of datetime (uses pickle rather than json)
        #        if deemed necessary)
        # * db entry next_fetch_attempt set, and in the future

        # commonly happens when queue_feeds.py restarted
        # (setting queued = False, but not fully clearing queue?)

        if (not f.active or
            not f.system_enabled or
            not f.queued or
            (qtime and f.last_fetch_attempt != qtime) or
                (f.next_fetch_attempt and f.next_fetch_attempt > now)):
            feeds_incr('insane')
            logger.info(
                f"insane: act {f.active} ena {f.system_enabled} qd {f.queued} nxt {f.next_fetch_attempt} last {f.last_fetch_attempt} qt {qtime}")
            return

        # mark time of actual attempt (start)
        # above `f.last_fetch_attempt != qtime` depends on this
        # (could also replace "queued" with a tri-state: idle, queued, active):
        f.last_fetch_attempt = now
        feed = f.as_dict()      # code below expects dict
        session.commit()
        # end with session.begin() & with_for_update

    try:
        if feed['next_fetch_attempt']:
            # delay from when ready to queue to start of processing
            stats.timing_td('start_delay', now - feed['next_fetch_attempt'])
    except BaseException as e:
        logger.debug(f"start_delay timing: {e}")

    try:
        # first thing is to fetch the content
        logger.info(f"Working on feed {feed_id}")
        response = _fetch_rss_feed(feed)
    except Exception as exc:
        logger.warning(f" Feed {feed_id}: fetch failed {exc}")
        update_feed(session, feed_id, Status.SOFT, f"fetch: {exc}", now)

        # NOTE!! try to limit cardinality of status: (eats stats
        # storage and graph colors), so not doing detailed breakdown
        # for starters (full info available in fetch_event rows).

        # Do this earlier to include more human readable fetch attempt note??
        es = str(exc)
        if 'ConnectionPool' in es:  # use isinstance on exc?!
            feeds_incr('conn_err')
        else:
            feeds_incr('fetch_err')
        return

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
        logger.info(
            f"  Feed {feed_id} - skipping, bad response {rsc} at {rurl}")
        update_feed(session, feed_id, status, f"HTTP {rsc} / {rurl}", now)

        # limiting tag cardinality, only a few, common codes for now.
        # NOTE! 429 is "too many requests"
        # It's possible 403 (Forbidden) is also used that way???
        if rsc in (403, 404, 429):
            feeds_incr(f"http_{rsc}")
        else:
            feeds_incr(f"http_{rsc//100}xx")
        return

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
    # XXX mypy infers that all values are datetime?!!!
    feed_col_updates: Dict[str, Any] = {
        'last_fetch_success': now  # HTTP fetch succeeded
    }

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
        # Maybe set a boolean column (via feed_col_updates)
        # "sends_not_modified" to note this feed sends 304 responses,
        # and use that as license use a smaller minimum poll interval?
        logger.info(f"  Feed {feed_id} - skipping, file not modified")
        update_feed(
            session,
            feed_id,
            Status.SUCC,
            "not modified",
            now,
            feed_col_updates)
        feeds_incr('not_mod')
        return

    # code below this point expects full body w/ RSS
    if response.status_code != 200:
        # should not get here!
        logger.error(
            f"  Feed {feed_id} - unexpected status {response.status_code}")

    # BAIL: no changes since last time
    # treated as success
    if new_hash == feed['last_fetch_hash']:
        # Maybe clear "sends_not_modified" column mentioned above??
        logger.info(f"  Feed {feed_id} - skipping, same hash")
        update_feed(
            session,
            feed_id,
            Status.SUCC,
            "same hash",
            now,
            feed_col_updates)
        feeds_incr('same_hash')
        return

    feed_col_updates['last_fetch_hash'] = new_hash

    # try to parse the content, parsing all the stories
    try:
        parsed_feed = feedparser.parse(response.text)
        if parsed_feed.bozo:
            raise RuntimeError(parsed_feed.bozo_exception)
    except Exception as e:
        # BAIL: couldn't parse it correctly
        logger.warning(f"Couldn't parse feed {feed_id}: {e}")
        update_feed(session, feed_id, Status.SOFT, f"parse: {e}", now)
        # split up into different counters if needed/desired
        # (beware label cardinality)
        feeds_incr('parse_err')
        return

    feeds_incr('ok')

    saved, skipped = save_stories_from_feed(session, now, feed, parsed_feed)

    # may update feed_col_updates dict (add new "name")
    check_feed_title(feed, parsed_feed, feed_col_updates)

    # see if feed indicates update period
    try:                        # paranoia
        update_period_mins = _feed_update_period_mins(parsed_feed)

        if update_period_mins is not None:
            period_str = dt.timedelta(seconds=update_period_mins * 60)
            logger.debug(f"  Feed {feed_id} update period {period_str}")
    except BaseException:
        logger.exception("update period")  # XXX debug only?
        update_period_mins = None

    feed_col_updates['update_minutes'] = update_period_mins
    update_feed(session, feed_id, Status.SUCC, f"{skipped} skipped / {saved} added",
                now, feed_col_updates)


def save_stories_from_feed(session: SessionType, now: dt.datetime, feed: Dict,
                           parsed_feed: feedparser.FeedParserDict) -> Tuple[int, int]:
    """
    Take parsed feed, so insert all the (valid) entries.
    returns (saved_count, skipped_count)
    """
    stats = Stats.get()

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
            # and skip very common homepage patterns:
            if mcmetadata.urls.is_homepage_url(link):
                logger.debug(f" * skip homepage URL: {link}")
                stories_incr('home')
                skipped_count += 1
                continue
            s = models.Story.from_rss_entry(feed['id'], now, entry)
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
                    logger.debug(
                        f" * skip duplicate title URL: {link} | {s.normalized_title_hash} | {s.sources_id}")
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
            #logger.exception(f"bad rss entry {link}")

            stories_incr('bad')
            skipped_count += 1
        except (IntegrityError, PendingRollbackError, UniqueViolation) as _:
            # expected exception - log and ignore
            logger.debug(
                f" * duplicate normalized URL: {s.normalized_url}")
            stories_incr('dupurl2')
            skipped_count += 1

    entries = len(parsed_feed.entries)
    logger.info(
        f"  Feed {feed['id']} - {entries} entries ({skipped_count} skipped)")
    saved_count = entries - skipped_count
    return saved_count, skipped_count


def check_feed_title(feed: Dict,
                     parsed_feed: feedparser.FeedParserDict,
                     feed_col_updates: Dict) -> None:
    # update feed title (if it has one and it changed)
    try:
        title = parsed_feed.feed.title
        if len(title) > 0:
            title = ' '.join(title.split())  # condense whitespace

            if title and feed['name'] != title:
                # use !r (repr) to display strings w/ quotes
                logger.info(
                    f" Feed {feed['id']} updating name from {feed['name']!r} to {title!r}")
                feed_col_updates['name'] = title
    except AttributeError:
        # if the feed has no title that isn't really an error, just skip safely
        pass
    except BaseException:
        # not REALLY worth pulling a fire alarm over, but still
        # should be fixed!
        logger.exception("check_feed_title")

################

# called via rq:
# MUST be run from rq SimpleWorker to achieve session caching!!!!


def feed_worker(feed_id: int, ts_iso: str) -> None:
    """
    Fetch a feed, parse out stories, store them
    :param self: this maintains the single session to use for all DB operations
    :param feed_id: integer Feed id
    :param ts_iso: str datetime.isoformat of time queued (Feed.last_fetch_attempt)
    """
    try:
        session = Session()
        setproctitle(f"{APP} {DYNO} feed {feed_id}")
        fetch_and_process_feed(session, feed_id, ts_iso)
    except BaseException:
        logger.exception("feed_worker")
