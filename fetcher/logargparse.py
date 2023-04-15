"""
argparser class with logging arguments for rss-fetcher scripts
"""

# NOTE! celery, flask, rq, uvicorn all use "click" for command line parsing (instead of argparse).
# WISH: add --config VAR=VALUE (overwrite environment)??

import argparse
import json
import logging
import logging.config
import os
import sys
from typing import Optional, Sequence

# PyPI:
import yaml

# local:
from fetcher import DYNO, VERSION
from fetcher.config import conf
import fetcher.path as path
import fetcher.sentry
import fetcher.stats

LEVELS = [level.lower() for level in logging._nameToLevel.keys()]

LOGGER_LEVEL_SEP = ':'

LEVEL_DEST = 'log_level'        # args entry name!

logger = logging.getLogger(__name__)


class LogArgumentParser(argparse.ArgumentParser):
    def __init__(self, prog: str, descr: str):
        super().__init__(prog=prog, description=descr)

        if DYNO.startswith('run.'):
            dyno = 'run.x'
        else:
            dyno = DYNO
        default_fname = f"{prog}.{dyno}.log"  # full path?

        # all loggers:
        self.add_argument('--verbose', '-v', action='store_const',
                          const='DEBUG', dest=LEVEL_DEST,
                          help="set default logging level to 'DEBUG'")
        self.add_argument('--quiet', '-q', action='store_const',
                          const='WARNING', dest=LEVEL_DEST,
                          help="set default logging level to 'WARNING'")
        self.add_argument('--list-loggers', action='store_true',
                          dest='list_loggers',
                          help="list all logger names and exit")
        self.add_argument('--log-config', action='store',
                          help="configure logging with .json, .yml, or .ini file",
                          metavar='LOG_CONFIG_FILE')
        self.add_argument('--log-file', default=default_fname, dest='log_file',
                          help=f"log file name (default: {default_fname})")
        self.add_argument('--log-level', '-l', action='store', choices=LEVELS,
                          dest=LEVEL_DEST, default=os.getenv(
                              'LOG_LEVEL', 'INFO'),
                          help="set default logging level to LEVEL")

        self.add_argument('--no-log-file', action='store_const',
                          const=None, dest='log_file',
                          help="don't log to a file")

        # set specific logger verbosity:
        self.add_argument('--logger-level', '-L', action='append',
                          dest='logger_level',
                          help=('set LOGGER (see --list-loggers) '
                                'verbosity to LEVEL (see --log-level)'),
                          metavar=f"LOGGER{LOGGER_LEVEL_SEP}LEVEL")

        self.add_argument('--set', '-S', action='append',
                          help=('set config/environment variable'
                                ' (may not effect all parameters)'),
                          metavar='VAR=VALUE')

        self.add_argument('--version', '-V', action='version',
                          version=f"rss-fetcher {prog} {VERSION}")

    # PLB: wanted to override parse_args, but couldn't get typing right for
    # mypy
    def my_parse_args(self, pid=False) -> argparse.Namespace:
        args = self.parse_args()

        if args.set:
            # sqlalchemy.engine:INFO should log SQL
            for vv in args.set:
                var, val = vv.split('=', 1)
                os.environ[var] = val

        if args.list_loggers:
            for name in sorted(logging.root.manager.loggerDict):
                print(name)
            sys.exit(0)

        level = getattr(args, LEVEL_DEST)
        if level is None:
            level = 'INFO'
        else:
            level = level.upper()

        log_format = '%(asctime)s | %(levelname)s | %(name)s | '
        if pid:
            log_format += '%(process)d | '
        log_format += '%(message)s'
        logging.basicConfig(format=log_format, level=level)

        if args.log_config:
            # lifted from uvicorn/config.py:
            if args.log_config.endswith(".json"):
                with open(args.log_config) as file:
                    loaded_config = json.load(file)
                    logging.config.dictConfig(loaded_config)
            elif args.log_config.endswith((".yaml", ".yml")):
                with open(args.log_config) as file:
                    loaded_config = yaml.safe_load(file)
                    logging.config.dictConfig(loaded_config)
            else:
                # See the note about fileConfig() here:
                # https://docs.python.org/3/library/logging.config.html#configuration-file-format
                logging.config.fileConfig(args.log_config,
                                          disable_existing_loggers=False)

        if args.logger_level:
            for ll in args.logger_level:
                logger_name, level = ll.split(LOGGER_LEVEL_SEP, 1)
                # XXX check logger_name in logging.root.manager.loggerDict??
                # XXX check level.upper() in LEVELS?
                logging.getLogger(logger_name).setLevel(level.upper())

        # was once inline code in fetcher.tasks
        if args.log_file:
            path.check_dir(path.LOG_DIR)
            log_path = os.path.join(path.LOG_DIR, args.log_file)

            # rotate file after midnight (UTC), keep 7 old files
            fileHandler = logging.handlers.TimedRotatingFileHandler(
                log_path, when='midnight', utc=True,
                backupCount=conf.LOG_BACKUP_COUNT)
            fileHandler.setFormatter(logging.Formatter(log_format))
            logging.getLogger(None).addHandler(
                fileHandler)  # attach to root logger

        # log startup banner and deferred config msgs
        conf.start(self.prog, self.description)

        fetcher.sentry.init()

        if args.log_file:       # after startup banner
            logger.info(f"Logging to {log_path}")
        else:
            logger.info("Not logging to a file")

        # NOTE! pushing this down (from script top level)
        # may have been a mistake: Trying to pass a "workers"
        # argument to uvicorn.run (needs to get app as "server.app")
        # launches new processes without Stats.init being called.

        # context where multiple processes were launched
        # via a library that spawned workers as processes
        fetcher.stats.Stats.init(self.prog)

        return args


if __name__ == '__main__':
    p = LogArgumentParser('main', 'test program')
    args = p.my_parse_args()

    logger.debug('debug')
    logger.info('info')
    logger.warning('warning')
    logger.error('error')
    logger.critical('critical')
