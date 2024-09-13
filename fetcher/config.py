"""
RSS Fetcher Configuration

Fetch configuration values with defaulting,
optionally log only the ones that are used.
Started 9/26/2022
"""

# Goals:
# 0. Log program program specific (optional) banner before config values
# 1. Maintains centralized defaulting of config values
# 2. Logs each variable once, and ONLY if requested
# 3. conf.TYPO causes error rather than silent failure

import logging
import os
import sys
from typing import Any, Dict, List, Optional

# PyPI
from dotenv import load_dotenv

# local
from fetcher import VERSION

load_dotenv()  # load config from .env file (local) or env vars (production)

logger = logging.getLogger(__name__)

# Conf variables implemented as property functions.

#  Could also be done with instances of subclasses of a MemoizedConfig
#  "descriptor" class with a __get__ method that checks if a value has
#  been fetched and memoized (in self.value), and if not, calls a
#  (subclass specific) "getvalue" method.  The Only CLEAR advantage of
#  descriptor objects is that they work on bare class (properties
#  require an instance), which would avoid madness (duplicate
#  messages) if someone ever made a second _Config object instance.

# conf_thing functions return properties for _Config class members
# used in class definition as MEMBER = conf_....('NAME', ....)

# The "confobj" argument passed to the getter functions
# is the (one) _Conf class instance, since they're being
# called to access properties of that object.


def conf_default(name: str, defval: str) -> property:
    """
    return property function for
    config variable with default (if not set)
    """

    def getter(confobj: '_Config') -> Any:
        if name in confobj.values:
            value = confobj.values[name]  # cached value
        else:
            value = os.environ.get(name, defval)
            confobj._log(name, value)  # log first time only
        return value
    return property(getter)


def conf_bool(name: str, defval: bool) -> property:
    """
    return property function for
    config variable with boolean value
    tries to be liberal in what it accepts:
    True values: non-zero integer, true, t, on (case insensitive)
    """

    def getter(confobj: '_Config') -> bool:
        if name in confobj.values:
            value = bool(confobj.values[name])  # cached value
        else:
            v = os.environ.get(name)
            if v is None:
                value = defval
            else:
                v = v.strip().rstrip().lower()
                if v.isdigit():
                    value = bool(int(v))
                else:
                    value = v in ['true', 't', 'on']  # be liberal
                confobj._log(name, value)
        return value
    return property(getter)


def conf_int(name: str, defval: int) -> property:
    """
    return property function for
    Integer valued configuration variable, with default value
    (could add limits)
    """

    def getter(confobj: '_Config') -> int:
        if name in confobj.values:
            value = int(confobj.values[name])  # cached value
        else:
            try:
                value = int(os.environ.get(name, defval))
            except ValueError:
                value = defval
            confobj._log(name, value)  # log first time only
        return value
    return property(getter)


def conf_optional(name: str, hidden: bool = False) -> property:
    """
    return property function for
    optional configuration variable (returns None if not set, does not log)
    """

    def getter(confobj: '_Config') -> Any:
        if name in confobj.values:
            value = confobj.values[name]  # cached value
        else:
            value = confobj.values[name] = os.environ.get(name)
            if value is None:   # optional: log only if set
                confobj._set(name, value)
            else:
                confobj._log(name, value, hidden)  # log first time only
        return value
    return property(getter)


def conf_required(name: str) -> property:
    """
    return property function for required config:
    fatal if Conf.MEMBER referenced, but environment variable not set
    """

    def getter(confobj: '_Config') -> Any:
        if name not in os.environ:
            logger.error(f"{name} not set.")
            sys.exit(1)
        if name in confobj.values:
            value = confobj.values[name]  # cached value
        else:
            value = os.environ.get(name)
            confobj._log(name, value)  # log first time only
        return value
    return property(getter)


# default value for DEFAULT_INTERVAL_MINS if not configured:
_DEFAULT_DEFAULT_INTERVAL_MINS = 6 * 60

# default value for MINIMUM_INTERVAL_MINS if not configured:
_DEFAULT_MINIMUM_INTERVAL_MINS = _DEFAULT_DEFAULT_INTERVAL_MINS

# default value for MAXIMUM_INTERVAL_MINS if not configured:
_DEFAULT_MAXIMUM_INTERVAL_MINS = 24 * 60

# default value for MAXIMUM_BACKOFF_MINS if not configured:
_DEFAULT_MAXIMUM_BACKOFF_MINS = _DEFAULT_MAXIMUM_INTERVAL_MINS

# default value for AUTO_ADJUST_MAX_POLL_MINUTES if not configured:
_DEFAULT_AUTO_ADJUST_MAX_POLL_MINUTES = _DEFAULT_MAXIMUM_INTERVAL_MINS

# default maximum for auto-adjust:


class _Config:                  # only instantiated in this file
    """
    Configuration with logging on first access.

    All "members" are property functions
    (only work on an instance of this class)
    and there should only ever be ONE instance of this class!
    """

    def __init__(self) -> None:
        self.values: Dict[str, Any] = {}  # cache
        self.engine = None
        self.msgs: List[str] = []  # saved initial log messages
        self.logging = False

    def _set(self, name: str, value: Any) -> None:
        self.values[name] = value

    def _log(self, name: str, value: Any, hidden: bool = False) -> None:
        """
        set and log name & value
        """
        self._set(name, value)
        if hidden:
            value = '(hidden)'
        msg = f"{name}: {value}"
        if self.logging:
            logger.info(msg)
        else:
            self.msgs.append(msg)

    def start(self, prog: Optional[str], descr: Optional[str]) -> None:
        """
        Optionally log start message with any saved messages.
        Called from LogArgumentParser.parse_args after logger setup.
        """
        if prog:
            # GIT_REV set by Dokku
            git_rev = os.environ.get('GIT_REV', '(GIT_REV not set)')

            logger.info(
                "------------------------------------------------------------------------")

            logger.info(f"Starting {prog} version {VERSION} {git_rev}")
            for msg in self.msgs:
                logger.info(msg)
            self.logging = True

    # config variable properties in alphabetical order
    # (maybe split up into section by script??)

    # maximum absoulte deviation in minutes since last
    # successful poll under which to look at duplicate percentage
    # (needs to be larger than queue_feeds.py queuing interval)
    AUTO_ADJUST_MAX_DELTA_MIN = conf_int('AUTO_ADJUST_MAX_DELTA_MIN', 20)

    # maximum percentage of good URLs to allow to be duplicates before
    # considering adjusting poll_minutes up.  Lowering this number
    # makes auto-adjust (up/longer) more agressive.  No stories
    # returned, or no change in feed document are counted as 100%.
    # NOTE: Lowering to 90 would only trigger for with feeds returning
    # 10 or more stories, 80% when 5 or more stories, 75% when 4 or
    # more, 66% when 3 or more....
    AUTO_ADJUST_MAX_DUPLICATE_PERCENT = conf_int(
        'AUTO_ADJUST_MAX_DUPLICATE_PERCENT', 67)

    # maximum poll interval when auto-adjusting
    AUTO_ADJUST_MAX_POLL_MINUTES = conf_int('AUTO_ADJUST_MAX_POLL_MINUTES',
                                            _DEFAULT_AUTO_ADJUST_MAX_POLL_MINUTES)

    # minimum percentage of good URLs that must be duplicates to
    # insure feed poll interval is small enough, else auto-adjust
    # poll_minutes down: Raising this number makes auto-adjust
    # (down/shorter) more agressive.
    AUTO_ADJUST_MIN_DUPLICATE_PERCENT = conf_int(
        'AUTO_ADJUST_MIN_DUPLICATE_PERCENT', 33)

    # minimum poll interval when auto-adjusting
    # (but not lower than Feed.update_period)
    AUTO_ADJUST_MIN_POLL_MINUTES = conf_int('AUTO_ADJUST_MIN_POLL_MINUTES', 10)

    # number of minutes to reduce poll_rate by when auto-adjusting down.
    # also used for SOME increases, see AUTO_ADJUST_SMALL_{DAYS,MINS}.
    AUTO_ADJUST_MINUTES = conf_int('AUTO_ADJUST_MINUTES', 60)

    # number of days after last new stories seen (or feed creation)
    # in which to use AUTO_ADJUST_SMALL_MINUTES when auto-adjusting up.
    # after AUTO_ADJUST_SMALL_DAYS have passed, use AUTO_ADJUST_MINUTES.
    AUTO_ADJUST_SMALL_DAYS = conf_int('AUTO_ADJUST_SMALL_DAYS', 31)

    # number of minutes to increase poll_rate by when auto-adjusting
    # up/longer and new stories seen within AUTO_ADJUST_SMALL_DAYS
    # (adjust up by small increments when feed is returning stories)
    AUTO_ADJUST_SMALL_MINS = conf_int('AUTO_ADJUST_SMALL_MINS', 10)

    # keep this above the number of workers (initially 2x)
    DB_POOL_SIZE = conf_int('DB_POOL_SIZE', 32)

    # default requeue interval (if Feed.update_minutes not set)
    DEFAULT_INTERVAL_MINS = conf_int('DEFAULT_INTERVAL_MINS',
                                     _DEFAULT_DEFAULT_INTERVAL_MINS)

    # poll interval for short, fast feeds (used by scripts.poll_update)
    FAST_POLL_MINUTES = conf_int('FAST_POLL_MINUTES', 120)

    # number of fetch_event rows to keep for each feed
    FETCH_EVENT_ROWS = conf_int('FETCH_EVENT_ROWS', 30)

    # Use saved ETag or Last-Modified for conditional feed fetch.
    # Some feeds return same ETag and/or Last-Modified even
    # when feed has changed, so this is disabled by default!
    # ETag may be useless, but could consider using Last-Modified
    # if the value isn't too long ago????
    HTTP_CONDITIONAL_FETCH = conf_bool('HTTP_CONDITIONAL_FETCH', False)

    # True to keep Connection header.
    # requests defaults to "Connection: keep-alive" and
    # connections for sites served by Aakamai (npr.org) hang!
    HTTP_KEEP_CONNECTION_HEADER = conf_bool(
        'HTTP_KEEP_CONNECTION_HEADER', False)

    # number of old log files to keep
    LOG_BACKUP_COUNT = conf_int('LOG_BACKUP_COUNT', 7)

    # Number of failures before disabling feed. A surprising number of
    # feeds come back from what looks like death (including 404, host
    # not found, HTML).  Was originally 4, raised to 10, and then 30.
    # NOTE! "soft" and "temporary" failures increment
    # last_fetch_failures by fractional values.
    MAX_FAILURES = conf_int('MAX_FAILURES', 30)

    # maximum length URL to accept from feeds
    MAX_URL = conf_int('MAX_URL', 2048)

    # maximum delay when backing off
    # (needed with higher MAX_FAILURES)
    MAXIMUM_BACKOFF_MINS = conf_int('MAXIMUM_BACKOFF_MINS',
                                    _DEFAULT_MAXIMUM_BACKOFF_MINS)

    # maximum interval to accept from sy:update{Period,Frequency}
    # (also used for maximum auto-adjust value)
    MAXIMUM_INTERVAL_MINS = conf_int('MAXIMUM_INTERVAL_MINS',
                                     _DEFAULT_MAXIMUM_INTERVAL_MINS)

    # For querying search.mediacloud.org for updates to feeds table
    MCWEB_URL = conf_default('MCWEB_URL', 'https://search.mediacloud.org')
    MCWEB_TIMEOUT = conf_int('MCWEB_TIMEOUT', 60)
    MCWEB_TOKEN = conf_optional('MCWEB_TOKEN', hidden=True)

    # minimum requeue interval (used to clamp sy:updatePeriod/Frequency)
    # if server has never sent a 304 "Not Modified" response,
    # and auto-adjust has never been applied:
    MINIMUM_INTERVAL_MINS = conf_int('MINIMUM_INTERVAL_MINS',
                                     _DEFAULT_MINIMUM_INTERVAL_MINS)

    # days back to check for duplicate story URLs/titles
    NORMALIZED_TITLE_DAYS = conf_int('NORMALIZED_TITLE_DAYS', 7)

    # number of parallel fetches for feeds that have the same scoreboard entry.
    # with current (c)lock-step rate control, concurrency will only happen
    # when a fetch takes longer than RSS_FETCH_FEED_SECS.  This is likely
    # to happen if the server is down, in which case high concurrency values
    # will only tie up more workers.
    RSS_FETCH_FEED_CONCURRENCY = conf_int('RSS_FETCH_FEED_CONCURRENCY', 2)

    # minimum interval between starting fetches for the same scoreboard entry.
    # NOTE:
    # max_feeds_per_source/(60/RSS_FETCH_FEED_SECS*RSS_FETCH_FEED_CONCURRENCY)
    # must be less than 1440 to fetch each feed JUST once a day!!
    # (source 314, with 14K feeds is a problem!).
    # Make a float to allow more than 60 fetches/second
    # (or change parameter to RSS_FETCH_FEED_PER_MINUTE?)
    RSS_FETCH_FEED_SECS = conf_int('RSS_FETCH_FEED_SECS', 5)  # 5s = 12/min

    # ready items for fetch to keep "on hand": if too small could
    # return ONLY unissuable feeds.  more than can be fetched in
    # DB_READY_SEC wastes effort, *AND* the current algorithm is O(n^2)
    # in the WORST case (lots of unissuable feeds)!!!  In April
    # 2023 when this comment was written, there were 15 sources with
    # OVER 900 active/enabled feeds (one of those over 12K, and two
    # over 2K)!!
    RSS_FETCH_READY_LIMIT = conf_int('RSS_FETCH_READY_LIMIT', 2000)

    # timeout in sec. for fetching an RSS file
    RSS_FETCH_TIMEOUT_SECS = conf_int('RSS_FETCH_TIMEOUT_SECS', 30)

    # number of worker processes
    RSS_FETCH_WORKERS = conf_int('RSS_FETCH_WORKERS', 2)  # raise in production

    # user/password for Basic Authentication for rss-fetcher API service
    RSS_FETCHER_USER = conf_optional('RSS_FETCHER_USER', hidden=True)
    RSS_FETCHER_PASS = conf_optional('RSS_FETCHER_PASS', hidden=True)

    # days of RSS output files to generate
    # (also retention limit on stories)
    RSS_OUTPUT_DAYS = conf_int('RSS_OUTPUT_DAYS', 14)

    # enable saving input (RSS) files that fail to parse
    # (one per feed), plus metadata
    SAVE_PARSE_ERRORS = conf_bool('SAVE_PARSE_ERRORS', False)

    # save input rss files (one per source) plus metadata for debug
    SAVE_RSS_FILES = conf_bool('SAVE_RSS_FILES', False)

    SENTRY_DSN = conf_optional('SENTRY_DSN')
    SENTRY_ENV = conf_optional('SENTRY_ENV')

    # skip all pages that look like "home pages"
    SKIP_HOME_PAGES = conf_bool('SKIP_HOME_PAGES', False)

    SQLALCHEMY_DATABASE_URI = conf_required('DATABASE_URL')

    # Display generated SQL
    SQLALCHEMY_ECHO = conf_bool('SQLALCHEMY_ECHO', False)

    # required if STATSD_URL set
    STATSD_PREFIX = conf_optional('STATSD_PREFIX')

    # set by dokku-graphite plugin
    STATSD_URL = conf_optional('STATSD_URL')

    # rq default is 180 sec (3m)
    TASK_TIMEOUT_SECONDS = conf_int('TASK_TIMEOUT_SECONDS', 3 * 60)

    # if True, never disable bad feeds:
    UNDEAD_FEEDS = conf_bool('UNDEAD_FEEDS', True)

    # if UNDEAD_FEEDS, max delay between polls:
    UNDEAD_FEED_MAX_DAYS = conf_int('UNDEAD_FEED_MAX_DAYS', 30)

    VERIFY_CERTIFICATES = conf_bool('VERIFY_CERTIFICATES', True)


conf = _Config()


def fix_database_url(url: str) -> str: # convert to psycopg2 config
    # "postgres:" URLs deprecated in SQLAlchemy 1.4 (wants postgresql)
    scheme, path = url.split(':', 1)
    if scheme in ('postgresql', 'postgres'):
        url = 'postgresql+psycopg:' + path
    return url


if __name__ == '__main__':  # move to a test file?
    logging.basicConfig(level='INFO')
    a = conf.RSS_FETCH_TIMEOUT_SECS    # should get default, log after start

    # should output start message, plus RSS_FETCH_TIMEOUT_SECS
    conf.start("testing", "description of test program")

    # second access: should not log
    a = conf.RSS_FETCH_TIMEOUT_SECS

    # optional, should log only if set
    a = conf.SENTRY_DSN

    try:
        a = conf.ZZZ            # type: ignore
        assert False
    except AttributeError:
        pass
