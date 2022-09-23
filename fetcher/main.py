"""
main program for rss-fetcher (logs startup message)
(instead of "celery" command)
"""

import sys
import logging

# PyPI
from celery.__main__ import main


# rss fetcher
import fetcher                  # logs PROGRAM & params

if __name__ == '__main__':
    sys.exit(main())
