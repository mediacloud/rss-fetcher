"""
Startup script for rss-fetcher worker

NOTE! With rq, each invocation of this script runs ONE worker process,
so the number of workers is controlled by
"dokku ps:scale rss-fetcher NUMBER"

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
    fetcher.tasks.open_log_file()
    worker()
