"""
Startup script for rss-fetcher worker

NOTE! With rq, each invocation of this script runs ONE worker process,
so the number of workers is controlled by
"dokku ps:scale rss-fetcher NUMBER"

"""

# local
from fetcher.logargparse import LogArgumentParser
import fetcher.queue
from fetcher.stats import Stats
import fetcher.tasks

SCRIPT = 'worker'

if __name__ == '__main__':
    p = LogArgumentParser(SCRIPT, 'Queue Worker')

    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    Stats.init(SCRIPT)
    fetcher.queue.worker()
