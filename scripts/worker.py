"""
Startup script for rss-fetcher worker
"""

# local
from fetcher.queue import worker
from fetcher.stats import Stats
import fetcher.tasks

if __name__ == '__main__':
    Stats.init('worker')
    worker()
