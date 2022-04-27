import os
import logging
import sys
from dotenv import load_dotenv
from flask import Flask
from sentry_sdk.integrations.flask import FlaskIntegration
# from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk import init
from sqlalchemy import create_engine

VERSION = "0.4.0"

load_dotenv()  # load config from .env file (local) or env vars (production)

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path_to_log_dir = os.path.join(base_dir, 'logs')

# set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(name)s | %(message)s')
logger = logging.getLogger(__name__)
logger.info("------------------------------------------------------------------------")
logger.info("Starting up MC Backup RSS Fetcher v{}".format(VERSION))

# read in environment variables
BROKER_URL = os.environ.get('BROKER_URL', None)
if BROKER_URL is None:
    logger.error("No BROKER_URL env var specified. Pathetically refusing to start!")
    sys.exit(1)
logger.info("  Queue at {}".format(BROKER_URL))

MAX_FEEDS = int(os.environ.get('MAX_FEEDS', 10000))

SENTRY_DSN = os.environ.get('SENTRY_DSN', None)  # optional
if SENTRY_DSN:
    init(dsn=SENTRY_DSN, release=VERSION,
         # integrations=[FlaskIntegration(), CeleryIntegration()])
         integrations=[FlaskIntegration()])
    logger.info("  SENTRY_DSN: {}".format(SENTRY_DSN))
else:
    logger.info("  Not logging errors to Sentry")

SQLALCHEMY_DATABASE_URI = os.environ['DATABASE_URL']
if SQLALCHEMY_DATABASE_URI is None:
    logger.error("  No SQLALCHEMY_DATABASE_URI is specified. Bailing because we can't save things to a DB for tracking")
    sys.exit(1)
engine = create_engine(SQLALCHEMY_DATABASE_URI, pool_size=10)

RSS_FILE_PATH = os.environ['RSS_FILE_PATH']
if RSS_FILE_PATH is None:
    logger.error("  You must set RSS_FILE_PATH env var to tell us where to store generated RSS files")
    sys.exit(1)


def create_flask_app() -> Flask:
    """
    Create and configure the Flask app. Standard practice is to do this in a factory method like this.
    :return: a fully configured Flask web app
    """
    return Flask(__name__)
