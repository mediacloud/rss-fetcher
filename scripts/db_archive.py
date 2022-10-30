"""
top level script to archive and remove old database table entries
to prevent growth without bounds

NOTE! Output filenames contain time of script start;
does not indicate file contents
"""

# maybe keep N rows for each feed in fetch_events???

import datetime as dt
import logging
import os.path
import subprocess

from fetcher.config import conf
from fetcher.logargparse import LogArgumentParser
import fetcher.path as path

SCRIPT = 'db_archive'

logger = logging.getLogger(SCRIPT)
# stats = Stats.init(SCRIPT)  # not yet?

SQLALCHEMY_DATABASE_URI = conf.SQLALCHEMY_DATABASE_URI

def logsize(fname: str) -> None:
    try:
        st = os.stat(fname)
        logger.info(f"{fname}: {st.st_size} bytes")
    except BaseException as e:
        logger.error(f"stat {fname}: {e}")

def runlog(*cmdline) -> bool:
    """
    run command; log stdout/err
    """
    # capture stdout/stderr to one string
    # NOTE! shell=False make safer (args not evaluated by shell)
    ret = subprocess.run(cmdline, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
    for line in ret.stdout.decode('utf-8').split('\n'):
        if line:
            logger.info(f"{cmdline[0]}: {line}")
    return ret.returncode == 0

def dump(table: str, where: str, now: str, delete: bool) -> bool:
    path.check_dir(path.DB_ARCHIVE_DIR)
    fname = os.path.join(path.DB_ARCHIVE_DIR, f"{table}.{now}")
    with open(fname, "wb") as output:
        logger.info(f"output to {fname}")
        sql = f"SELECT * FROM {table} WHERE {where};"
        logger.debug(f"SQL: {sql}")
        # XXX create pipeline: psql | gzip > fname?
        # XXX capture stderr & log??
        ret = subprocess.run(
            ['psql', '--csv', SQLALCHEMY_DATABASE_URI, '-c', sql],
            stdout=output, shell=False)
        logger.debug(f"return code {ret.returncode}")
        logsize(fname)

    if ret.returncode != 0:
        logger.error(sql)
        return False

    if not runlog('gzip', '-fv', fname):
        return False
    logsize(fname + '.gz')

    if not delete:
        return True

    sql = f"DELETE FROM {table} WHERE {where};"
    logger.debug(f"SQL: {sql}")
    return runlog('psql', SQLALCHEMY_DATABASE_URI, '-c', sql)


if __name__ == '__main__':
    p = LogArgumentParser(SCRIPT, 'archive stories and fetch_events tables')
    p.add_argument('--story-days', type=int, default=conf.RSS_OUTPUT_DAYS,
                   help="number of days of stories table rows to keep")
    p.add_argument('--event-days', type=int, default=conf.FETCH_EVENT_DAYS,
                   help="number of days of fetch_events table rows to keep")
    p.add_argument('--delete', action='store_true', default=False,
                   help="delete rows after writing files")
    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    now = dt.datetime.utcnow()
    fname = now.strftime('%Y-%m-%d-%H-%M-%S')

    limit = now.date() - dt.timedelta(days=args.event_days)
    limit_str = limit.isoformat()
    # XXX could archive/delete all but last N rows
    dump('fetch_events', f"created_at < '{limit_str}'", fname, args.delete)

    limit = now.date() - dt.timedelta(days=args.story_days)
    limit_str = limit.isoformat()
    dump('stories', f"fetched_at < '{limit_str}'", fname, args.delete)
