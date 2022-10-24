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


def conf_optional(name: str) -> property:
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
                confobj._log(name, value)  # log first time only
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
_DEFAULT_DEFAULT_INTERVAL_MINS = 12 * 60

# default value for MINIMUM_INTERVAL_MINS if not configured:
_DEFAULT_MINIMUM_INTERVAL_MINS = _DEFAULT_DEFAULT_INTERVAL_MINS

# default value for MINIMUM_INTERVAL_MINS_304 if not configured:
_DEFAULT_MINIMUM_INTERVAL_MINS_304 = _DEFAULT_DEFAULT_INTERVAL_MINS


class _Config:                  # only instantied in this file
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

    def _log(self, name: str, value: Any) -> None:
        """
        set and log name & value
        """
        self._set(name, value)
        msg = f"{name}: {value}"
        if self.logging:
            logger.info(msg)
        else:
            self.msgs.append(msg)

    def start(self, prog: Optional[str], descr: Optional[str]) -> None:
        """
        optionally log start message with any saved messages
        called from LogArgumentParser.parse_args
        after logger setup
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

    # days to check in DB: only needed until table partitioned by day?
    DAY_WINDOW = conf_int('DAY_WINDOW', 7)

    # keep this above the number of workers (initially 2x)
    DB_POOL_SIZE = conf_int('DB_POOL_SIZE', 32)

    # default requeue interval (if Feed.update_minutes not set)
    DEFAULT_INTERVAL_MINS = conf_int('DEFAULT_INTERVAL_MINS',
                                     _DEFAULT_DEFAULT_INTERVAL_MINS)

    # failures before disabling feed
    MAX_FAILURES = conf_int('MAX_FAILURES', 4)

    # feeds to queue before quitting (if not looping)
    MAX_FEEDS = conf_int('MAX_FEEDS', 10000)

    # minimum requeue interval (used to clamp sy:updatePeriod/Frequency)
    MINIMUM_INTERVAL_MINS = conf_int('MINIMUM_INTERVAL_MINS',
                                     _DEFAULT_MINIMUM_INTERVAL_MINS)

    # minimum requeue interval (if feed sends 304 "Not Modified"
    # responses) (allow honoring shorter intervals advertised by feed
    # when cost is lower).  An initial look shows that the majority of
    # feeds on servers returning 304, have update periods that are an
    # hour or less; It's doubtful we would ever want to poll THAT
    # often.  CAUTION!  Faster polling could cause more 429 (throttling)
    # responses!
    MINIMUM_INTERVAL_MINS_304 = conf_int('DEFAULT_INTERVAL_MINS_304',
                                         _DEFAULT_MINIMUM_INTERVAL_MINS_304)

    # rq uses only redis for queues; use dokku-redis supplied URL
    REDIS_URL = conf_required('REDIS_URL')

    # timeout in sec. for fetching an RSS file
    RSS_FETCH_TIMEOUT_SECS = conf_int('RSS_FETCH_TIMEOUT_SECS', 30)

    # save input rss files (one per source) plus metadata for debug
    SAVE_RSS_FILES = conf_bool('SAVE_RSS_FILES', False)

    SENTRY_DSN = conf_optional('SENTRY_DSN')

    SQLALCHEMY_DATABASE_URI = conf_required('DATABASE_URL')


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
