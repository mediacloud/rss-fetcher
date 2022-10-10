import os
import logging
import sys

# PyPI
from dotenv import load_dotenv
from sentry_sdk import init
from sqlalchemy import create_engine

VERSION = "0.11.12"

load_dotenv()  # load config from .env file (local) or env vars (production)

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path_to_log_dir = os.path.join(base_dir, 'logs')

# set up logging
logger = logging.getLogger(__name__)

# PLB: used to have logging.basicConfig here, but call moved to fetcher.logargparse
# to give command line control of what gets logged.  This means the config logging
# below will not be seen, but I have plans to fix that. 10/10/22

logger.info("------------------------------------------------------------------------")
git_rev = os.environ.get('GIT_REV', '(not set)') # set by Dokku
logger.info(f"Starting version {VERSION} GIT_REV {git_rev}")


# read in environment variables
REDIS_URL = os.environ.get('REDIS_URL')

logger.info(f"  REDIS_URL {REDIS_URL}")

#BACKEND_URL = os.environ.get('BACKEND_URL', 'db+sqlite:///celery-backend.db')
#logger.info("  Queue backend at {}".format(BACKEND_URL))

def _get_env_int(name: str, defval: int) -> int:
    try:
        val = int(os.environ.get(name, defval))
    except ValueError:
        val = defval
    logger.info(f"  {name}: {val}")
    return val

# integer values params in alphabetical order
DAY_WINDOW = _get_env_int('DAY_WINDOW', 7) # days to check in DB: only needed until table partitioned by day?
DB_POOL_SIZE = _get_env_int('DB_POOL_SIZE', 32)  # keep this above the worker concurrency set in Procfile
DEFAULT_INTERVAL_MINS = _get_env_int('DEFAULT_INTERVAL_MINS', 12*60) # requeue interval
MINIMUM_INTERVAL_MINS = _get_env_int('MINIMUM_INTERVAL_MINS', DEFAULT_INTERVAL_MINS)

MAX_FAILURES = _get_env_int('MAX_FAILURES', 4) # failures before disabling feed
MAX_FEEDS = _get_env_int('MAX_FEEDS', 10000)   # feeds to queue before quitting
RSS_FETCH_TIMEOUT_SECS = _get_env_int('RSS_FETCH_TIMEOUT_SECS', 30) # timeout in sec. for fetching an RSS file

SENTRY_DSN = os.environ.get('SENTRY_DSN')  # optional
if SENTRY_DSN:
    init(dsn=SENTRY_DSN, release=VERSION)
    logger.info("  SENTRY_DSN: {}".format(SENTRY_DSN))
else:
    logger.info("  Not logging errors to Sentry")

SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
if not SQLALCHEMY_DATABASE_URI:
    logger.error("  No SQLALCHEMY_DATABASE_URI is specified. Bailing because we can't save things to a DB for tracking")
    sys.exit(1)
engine = create_engine(SQLALCHEMY_DATABASE_URI, pool_size=DB_POOL_SIZE)

RSS_FILE_PATH = os.environ.get('RSS_FILE_PATH')
if not RSS_FILE_PATH:
    logger.error("  You must set RSS_FILE_PATH env var to tell us where to store generated RSS files")
    sys.exit(1)

def _get_env_bool(name: str, defval: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        val = defval
    else:
        val = val.strip().rstrip().lower()
        if val.isdigit():
            val = bool(int(val))
        else:
            val = val in ['true', 't', 'on'] # be liberal
    logger.info(f"  {name}: {val}")
    return val

SAVE_RSS_FILES = _get_env_bool('SAVE_RSS_FILES', False)
