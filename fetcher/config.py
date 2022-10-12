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

# PyPI
from dotenv import load_dotenv

# local
from fetcher import VERSION

load_dotenv() # load config from .env file (local) or env vars (production)

logger = logging.getLogger(__name__)

# conf_XXX functions return property getters for Config members
# used in class definition as MEMBER = conf_....('NAME', ....)

def conf_default(name: str, defval: str):
    """
    return property function for
    config variable with default (if not set)
    """
    @property
    def getter(self):
        if name in self.values:
            value = self.values[name] # cached value
        else:
            value = os.environ.get(name, defval)
            self._log(name, value) # log first time only
        return value
    return getter

def conf_bool(name: str, defval: bool):
    """
    return property function for
    config variable with boolean value
    tries to be liberal in what it accepts:
    True values: non-zero integer, true, t, on (case insensitive)
    """
    @property
    def getter(self):
        if name in self.values:
            value = self.values[name] # cached value
        else:
            value = os.environ.get(name)
            if value is None:
                val = defval
            else:
                value = value.strip().rstrip().lower()
                if value.isdigit():
                    value = bool(int(value))
                else:
                    value = value in ['true', 't', 'on'] # be liberal
                self._log(name, value)
        return value
    return getter

def conf_int(name: str, defval: int) -> int:
    """
    return property function for
    Integer valued configuration variable, with default value
    (could add limits)
    """
    @property
    def getter(self):
        if name in self.values:
            value = self.values[name] # cached value
        else:
            try:
                value = int(os.environ.get(name, defval))
            except ValueError:
                value = defval
            self._log(name, value) # log first time only
        return value
    return getter

def conf_optional(name: str):
    """
    return property function for
    optional configuration variable (returns None if not set, does not log)
    """
    @property
    def getter(self):
        if name in self.values:
            value = self.values[name] # cached value
        else:
            value = self.values[name] = os.environ.get(name)
            if value is None:   # optional: log only if set
                self._set(name, value)
            else:
                self._log(name, value) # log first time only
        return value
    return getter

def conf_required(name):
    """
    return property function for required config:
    fatal if Conf.MEMBER referenced, but environment variable not set
    """
    @property
    def getter(self):
        if name not in os.environ:
            logger.error(f"{name} not set.")
            sys.exit(1)
        if name in self.values:
            value = self.values[name] # cached value
        else:
            value = os.environ.get(name)
            self._log(name, value) # log first time only
        return value
    return getter


_DEFAULT_DEFAULT_INTERVAL_MINS = 12*60
_DEFAULT_MINIMUM_INTERVAL_MINS = _DEFAULT_DEFAULT_INTERVAL_MINS

class _Config:                  # only instantied in this file
    """
    Configuration with logging
    """

    def __init__(self):
        self.values = {}        # cache
        self.engine = None
        self.msgs = []
        self.logging = False

    def _set(self, name, value):
        self.values[name] = value

    def _log(self, name, value):
        """
        set and log name & value
        """
        self._set(name, value)
        msg = f"{name}: {value}"
        if self.logging:
            logger.info(msg)
        else:
            self.msgs.append(msg)

    def start(self, prog, descr):
        """
        log start message with any saved messages
        called from LogArgumentParser.parse_args
        after logger setup
        """
        if prog:
            # GIT_REV set by Dokku; if not set
            # use `git rev-parse HEAD` for hash
            # test if clean?? import git; git.Repo(path).is_dirty()????
            git_rev = os.environ.get('GIT_REV', '(GIT_REV not set)')

            logger.info("------------------------------------------------------------------------")

            logger.info(f"Starting {prog} version {VERSION} {git_rev}")
            for msg in self.msgs:
                logger.info(msg)
            self.logging = True

    # config variables in alphabetical order
    # (maybe split up into section by script??)
    # creates properties acessible in INSTANCES only!

    # days to check in DB: only needed until table partitioned by day?
    DAY_WINDOW = conf_int('DAY_WINDOW', 7)

    # keep this above the number of workers (initially 2x)
    DB_POOL_SIZE = conf_int('DB_POOL_SIZE', 32)

    # default requeue interval (if Feed.update_minutes not set)
    DEFAULT_INTERVAL_MINS = conf_int('DEFAULT_INTERVAL_MINS',
                                     _DEFAULT_DEFAULT_INTERVAL_MINS)

    # failures before disabling feed
    MAX_FAILURES = conf_int('MAX_FAILURES', 4)

    # feeds to queue before quitting
    MAX_FEEDS = conf_int('MAX_FEEDS', 10000)

    # minimum requeue interval (used to clamp sy:updatePeriod/Frequency)
    MINIMUM_INTERVAL_MINS = conf_int('MINIMUM_INTERVAL_MINS', 
                                     _DEFAULT_DEFAULT_INTERVAL_MINS)

    # rq uses only redis for queues
    REDIS_URL = conf_required('REDIS_URL')

    # timeout in sec. for fetching an RSS file
    RSS_FETCH_TIMEOUT_SECS = conf_int('RSS_FETCH_TIMEOUT_SECS', 30)

    # where to save RSS files when SAVE_RSS_FILES enabled
    RSS_FILE_PATH = conf_required('RSS_FILE_PATH')

    # save rss files (one per source) plus metadata
    SAVE_RSS_FILES = conf_bool('SAVE_RSS_FILES', False)

    SENTRY_DSN = conf_optional('SENTRY_DSN')

    SQLALCHEMY_DATABASE_URI = conf_required('DATABASE_URL')
    

conf = _Config()

if __name__ == '__main__':
    logging.basicConfig(level='INFO')
    a = conf.RSS_FETCH_TIMEOUT_SECS    # should get default, log after start
    conf.start("Hello World") # should output message
    a = conf.RSS_FETCH_TIMEOUT_SECS    # should not log

    try:
        a = conf.SENTRY_DSN2
        assert False
    except AttributeError:
        pass

    try:
        a = conf.RSS_FILE_PATH
    except None:
        pass

    try:
        a = conf.ZZZ
    except AttributeError:
        pass
