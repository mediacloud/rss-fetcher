"""
Startup script for rss-fetcher worker
"""

# local
from fetcher.logargparse import LogArgumentParser
from fetcher.queue import worker
from fetcher.stats import Stats
import fetcher.tasks

if __name__ == '__main__':
    p = LogArgumentParser('worker', 'Queue Worker')
    # info logging before this call unlikely to be seen:
    args = p.parse_args()       # parse logging args, output start message

    Stats.init('worker')
    worker()
