"""
Startup script for rss-fetcher worker
"""

# local
from fetcher.logargparse import LogArgumentParser
from fetcher.queue import worker
from fetcher.stats import Stats
import fetcher.tasks

if __name__ == '__main__':
    p = LogArgumentParser('worker', 'queue worker')
    p.parse_args()              # parse logging args

    Stats.init('worker')
    worker()
