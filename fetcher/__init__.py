import os

VERSION = "0.11.12"

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path_to_log_dir = os.path.join(base_dir, 'logs')

# for SQLAlchemy engine:
# from fetcher.database.engine import engine
#
# all config moved to fetcher/config.py
# access via: "from fetcher import conf; conf.XYZ"

# used for feed_worker process title, sentry environment check
APP = os.environ.get('MC_APP', 'unknown-rss-fetcher')

# Dokku supplies worker.N:
DYNO = os.environ.get('DYNO', f"worker.{os.getpid()}")
