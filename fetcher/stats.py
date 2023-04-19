"""
Thin shim for statistics gathering.

Meant to be independent of stats gathering protocol/schema AND library.
ie; transparently handle statsd (with and without tag support) and prometheus
"""

import datetime as dt
import logging
from typing import Any, List, Optional, Tuple

# PyPi
import statsd                   # type: ignore[import]
from sqlalchemy.engine.url import make_url

from fetcher.config import conf

# PLB: I selected statsd_client
# [https://github.com/gaelen/python-statsd-client]
# as the simplest statsd client (no dependencies).

# The more venerable "statsd" package
# [https://github.com/jsocol/pystatsd]
# calls in requirements not used elsewhere, and
# the only upside seems to be support of "sets"

# See docs/stats.md for discussion of to name and organize statistics,
# the expected values for environment variables etc!!!

DEBUG = False
TAGS = False                    # get from env?? graphite >= 1.1.0 tags

logger = logging.getLogger(__name__)


class Stats:
    """
    hide protocol and library being used for statistics
    """

    _instance = None

    @classmethod
    def init(cls, component: str) -> 'Stats':
        """
        called from main program
        """
        if cls._instance:
            raise Exception(
                f"Stats.init called twice: {component}/{cls._instance.component}")
        cls._instance = cls(component, _init_ok=True)
        return cls._instance

    @classmethod
    def get(cls) -> 'Stats':
        """
        called from non-main modules
        """
        if not cls._instance:
            raise Exception("Stats.init not called")
        return cls._instance

    def __init__(self, component: str, _init_ok: bool = False):
        if not _init_ok:
            raise Exception("Call Stats.init")

        self.statsd: Optional[Any] = None
        self.host = self.port = self.prefix = None

        # STATSD URL set by dokku-graphite plugin
        e = conf.STATSD_URL
        if e:
            url = make_url(e)   # sqlalchemy URL parser
            # check if url.database == 'statsd'???
            self.host = url.host
            self.port = url.port

        prefix = conf.STATSD_PREFIX
        if prefix:
            self.prefix = f"{prefix}.{component}"

        if not self.host or not self.prefix:
            logger.warning("Not sending stats")
        # connect on demand

    def _connect(self) -> bool:
        # return if have statsd, or insufficient config
        if self.statsd:
            return True

        if not self.host or not self.prefix:
            return False

        try:
            self.statsd = statsd.StatsdClient(
                self.host, self.port, self.prefix)
            return True
        except BaseException:
            return False

    def _name(self, name: str, labels: List[Tuple[str, Any]] = []) -> str:
        """
        return a statsd suitable variable for name (may contain dots)
        and labels (in the prometheus sense), a list of [name,value] pairs.

        Sorts by dimension name to ensure consistent ordering.

        This MAY turn out to be a pain if you want to slice
        a chart based on one dimension (if that happens,
        add a no_sort argument to "inc" and "gauge", to pass here?
        """
        if labels:
            if TAGS:  # graphite 1.1 tags
                # https://graphite.readthedocs.io/en/latest/tags.html#tags
                # sorting may be unnecessary
                slabels = ';'.join([f"{name}={val}" for name, val in
                                    sorted(labels)])
                name = f"{name};{slabels}"
            else:  # pre-1.1 graphite w/o tag support (note sorting)
                # (no arbitrary tags in netdata)
                slabels = '.'.join([f"{name}_{val}" for name, val in
                                    sorted(labels)])
                name = f"{name}.{slabels}"
        if DEBUG:
            print("name", name)
        return name

    def incr(self, name: str, value: int = 1,
             labels: List[Tuple[str, Any]] = []) -> None:
        """
        Increment a counter
        (something that never decreases, like an odometer)

        Please use the convention that counter names end in "s".
        """
        for tries in (1, 2):
            if not self._connect():
                return

            if not self.statsd:
                return

            try:
                self.statsd.incr(self._name(name, labels), value)
                break
            except BaseException:
                self.statsd = None

    def gauge(self, name: str, value: float,
              labels: List[Tuple[str, Any]] = []) -> None:
        """
        Indicate value of a gauge
        (something that goes up and down, like a thermometer or speedometer)
        """
        for tries in (1, 2):
            if not self._connect():
                return

            if not self.statsd:
                return

            try:
                self.statsd.gauge(self._name(name, labels), value)
                break
            except BaseException:
                self.statsd = None

    def timing(self, name: str, sec: float,
               labels: List[Tuple[str, Any]] = []) -> None:
        """
        Report a timing (duration) in seconds
        """
        for tries in (1, 2):
            if not self._connect():
                return

            if not self.statsd:
                return

            try:
                # statsd timings are in ms
                self.statsd.timing(self._name(name, labels), sec * 1000)
                break
            except BaseException:
                self.statsd = None

    def timing_td(self, name: str, td: dt.timedelta,
                  labels: List[Tuple[str, Any]] = []) -> None:
        """
        Report a timing (duration) with a timedelta
        """
        self.timing(name, td.total_seconds(), labels)


if __name__ == '__main__':
    s = Stats.init('foo')
    s2 = Stats.get()
    assert s is s2
    s.incr('requests')
    s.gauge('bar', 33.33, labels=[('y', 2), ('x', 1)])
    s.timing('baz', 1.234)
