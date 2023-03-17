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

# default value for MINIMUM_INTERVAL_MINS_304 if not configured:
_DEFAULT_MINIMUM_INTERVAL_MINS_304 = _DEFAULT_DEFAULT_INTERVAL_MINS

# default value for MAXIMUM_INTERVAL_MINS if not configured:
_DEFAULT_MAXIMUM_INTERVAL_MINS = 24 * 60

# default value for MAXIMUM_BACKOFF_MINS if not configured:
_DEFAULT_MAXIMUM_BACKOFF_MINS = 2 * 24 * 60


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
        self.msgs: List[str] = []
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
    # creates properties acessible in INSTANCES only!
    # (descriptors work with bare class)

    # maximum deviation in minutes since last
    # successful poll under which to look at duplicate percentage
    # (needs to be larger than queue_feeds.py queuing interval)
    AUTO_ADJUST_MAX_DELTA_MIN = conf_int('AUTO_ADJUST_MAX_DELTA_MIN', 20)

    # maximum percentage of good URLs to allow to be duplicates before
    # considering adjusting poll_minutes up.  Lowering this number
    # makes auto-adjust (up/longer) more agressive.
    # ***MUST*** be > AUTO_ADJUST_MIN_DUPLICATE_PERCENT
    AUTO_ADJUST_MAX_DUPLICATE_PERCENT = conf_int(
        'AUTO_ADJUST_MAX_DUPLICATE_PERCENT', 100)

    # minimum percentage of good URLs that must be duplicates to
    # insure feed poll interval is small enough, else auto-adjust
    # poll_minutes down: Raising this number makes auto-adjust
    # (down/shorter) more agressive.
    # ***MUST*** be < AUTO_ADJUST_MAX_DUPLICATE_PERCENT
    AUTO_ADJUST_MIN_DUPLICATE_PERCENT = conf_int(
        'AUTO_ADJUST_MIN_DUPLICATE_PERCENT', 50)

    # minimum poll interval (if no published update period)
    AUTO_ADJUST_MIN_POLL_MINUTES = conf_int('AUTO_ADJUST_MIN_POLL_MINUTES', 60)

    # number of minutes to reduce poll_rate by when auto-adjusting
    # (could use a divisor for exponential backoff)
    AUTO_ADJUST_MINUTES = conf_int('AUTO_ADJUST_MINUTES', 60)

    # keep this above the number of workers (initially 2x)
    DB_POOL_SIZE = conf_int('DB_POOL_SIZE', 32)

    # default requeue interval (if Feed.update_minutes not set)
    DEFAULT_INTERVAL_MINS = conf_int('DEFAULT_INTERVAL_MINS',
                                     _DEFAULT_DEFAULT_INTERVAL_MINS)

    # poll interval for short, fast feeds (used by scripts.poll_update)
    FAST_POLL_MINUTES = conf_int('FAST_POLL_MINUTES', 120)

    # number of fetch_event rows to keep for each feed
    FETCH_EVENT_ROWS = conf_int('FETCH_EVENT_ROWS', 30)

    # Use saved ETag or Last-Modified for conditional feed fetch
    HTTP_CONDITIONAL_FETCH = conf_bool('HTTP_CONDITIONAL_FETCH', False)

    # number of old log files to keep
    LOG_BACKUP_COUNT = conf_int('LOG_BACKUP_COUNT', 7)

    # failures before disabling feed
    # a surprising number of feeds come back from what looks like death
    # (including 404, host not found, HTML)
    MAX_FAILURES = conf_int('MAX_FAILURES', 30)

    # feeds to queue before quitting (if not looping)
    MAX_FEEDS = conf_int('MAX_FEEDS', 10000)

    # maximum length URL to accept from feeds
    MAX_URL = conf_int('MAX_URL', 2048)

    # maximum delay when backing off
    # (needed with higher MAX_FAILURES)
    MAXIMUM_BACKOFF_MINS = conf_int('MAXIMUM_BACKOFF_MINS',
                                    _DEFAULT_MAXIMUM_BACKOFF_MINS)

    # maximum requeue interval (used to clamp sy:updatePeriod/Frequency)
    MAXIMUM_INTERVAL_MINS = conf_int('MAXIMUM_INTERVAL_MINS',
                                     _DEFAULT_MAXIMUM_INTERVAL_MINS)

    # For querying search.mediacloud.org for updates to feeds table
    MCWEB_URL = conf_default('MCWEB_URL', 'https://search.mediacloud.org')
    MCWEB_TIMEOUT = conf_int('MCWEB_TIMEOUT', 60)
    MCWEB_TOKEN = conf_optional('MCWEB_TOKEN', hidden=True)

    # minimum requeue interval (used to clamp sy:updatePeriod/Frequency)
    # if server has never sent a 304 "Not Modified" response.
    MINIMUM_INTERVAL_MINS = conf_int('MINIMUM_INTERVAL_MINS',
                                     _DEFAULT_MINIMUM_INTERVAL_MINS)

    # minimum requeue interval (if feed sends 304 "Not Modified"
    # responses) (allow honoring shorter intervals advertised by feed
    # when cost is lower).  An initial look shows that the majority of
    # feeds on servers returning 304, have update periods that are an
    # hour or less; It's doubtful we would ever want to poll THAT
    # often.  CAUTION!  Faster polling could cause more 429 (throttling)
    # responses!
    MINIMUM_INTERVAL_MINS_304 = conf_int('MINIMUM_INTERVAL_MINS_304',
                                         _DEFAULT_MINIMUM_INTERVAL_MINS_304)

    # days back to check for duplicate story URLs/titles
    NORMALIZED_TITLE_DAYS = conf_int('NORMALIZED_TITLE_DAYS', 7)

    # rq uses only redis for queues; use dokku-redis supplied URL
    REDIS_URL = conf_required('REDIS_URL')

    # timeout in sec. for fetching an RSS file
    RSS_FETCH_TIMEOUT_SECS = conf_int('RSS_FETCH_TIMEOUT_SECS', 30)

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

    VERIFY_CERTIFICATES = conf_bool('VERIFY_CERTIFICATES', True)


conf = _Config()

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
