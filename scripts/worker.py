"""
Startup script for rss-fetcher worker
"""

# PyPI
from celery.__main__ import main

from fetcher.stats import Stats

if __name__ == '__main__':
    Stats.init('worker')
    exit(main())
