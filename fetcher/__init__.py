# To avoid cluttering startup messages with config values that
# aren't actually used in every script, try to:

# 1. keep just invariant ("constant") values here (no object creation)
# 2. not import other files/modules
# 3. not take any actions that log (ALSO! try not to log before
# LogArgParse.my_parse_args called)

import os

VERSION = "0.14.5"

# paths moved to fetch.path

# for SQLAlchemy engine:
# from fetcher.database.engine import engine

# all config moved to fetcher/config.py
# access via: "from fetcher import conf; conf.XYZ"

# used for feed_worker process title, sentry environment check
APP = os.environ.get('MC_APP', 'unknown-rss-fetcher')

# Dokku supplies processname.N (or run.PID?):
DYNO = os.environ.get('DYNO', f"pid.{os.getpid()}")
