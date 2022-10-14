"""
argparser class with logging arguments for rss-fetcher scripts
"""

# NOTE! celery, flask, rq, uvicorn all use "click" for command line parsing (instead of argparse)
# so that may be worth examining???

import argparse
import json
import logging
import os
import sys

# PyPI:
import yaml

# local:
from fetcher import VERSION
from fetcher.config import conf

LEVELS = [level.lower() for level in logging._nameToLevel.keys()]

LOGGER_LEVEL_SEP = ':'


class LogArgumentParser(argparse.ArgumentParser):
    def __init__(self, prog, descr):
        super().__init__(prog=prog, description=descr)

        # all loggers:
        self.add_argument('--verbose', '-v', action='store_const',
                          const='DEBUG', dest='level',
                          help="set default logging level to 'DEBUG'")
        self.add_argument('--quiet', '-q', action='store_const',
                          const='WARNING', dest='level',
                          help="set default logging level to 'WARNING'")
        self.add_argument('--list-loggers', action='store_true',
                          dest='list_loggers',
                          help="list all logger names and exit")
        self.add_argument('--log-config', action='store',
                          help="configure logging with .json, .yml, or .ini file",
                          metavar='LOG_CONFIG_FILE')
        self.add_argument('--log-level', '-l', action='store', choices=LEVELS,
                          default=os.environ.get('LOG_LEVEL', 'INFO'),
                          help="set default logging level to LEVEL")

        # set specific logger verbosity:
        self.add_argument('--logger-level', '-L', action='append',
                          dest='logger_level',
                          help='set LOGGER (see --list-loggers) verbosity to LEVEL (see --level)',
                          metavar=f"LOGGER{LOGGER_LEVEL_SEP}LEVEL")

        self.add_argument('--version', '-V', action='version',
                          version=f"rss-fetcher {prog} {VERSION}")

    def parse_args(self):
        args = super().parse_args()

        if args.list_loggers:
            for name in sorted(logging.root.manager.loggerDict):
                print(name)
            sys.exit(0)

        level = args.level
        if level is None:
            level = 'INFO'
        else:
            level = level.upper()

        logging.basicConfig(
            format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            level=level)

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
            # sqlalchemy.engine:INFO should log SQL
            for ll in args.logger_level:
                logger_name, level = ll.split(LOGGER_LEVEL_SEP, 1)
                # XXX check logger_name in logging.root.manager.loggerDict??
                # XXX check level.upper() in LEVELS?
                logging.getLogger(
                    logger_name).handlers[0].setLevel(level.upper())

        # log startup banner and deferred config msgs
        conf.start(self.prog, self.description)

        fetcher.sentry.init()

        return args


if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    p = LogArgumentParser('main', 'test program')
    p.parse_args()

    logger.debug('debug')
    logger.info('info')
    logger.warning('warning')
    logger.error('error')
    logger.critical('critical')
