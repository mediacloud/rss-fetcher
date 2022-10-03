"""
Thin shim for statistics gathering.

Meant to be independent of stats gathering protocol/schema AND library.
ie; transparently handle statsd (with and without tag support) and prometheus
"""

import logging
import os

# PyPi
import statsd                   # pkg statsd_client

# PLB: I selected statsd_client
# [https://github.com/gaelen/python-statsd-client]
# as the simplest statsd client (no dependencies).

# The more venerable "statsd" package
# [https://github.com/jsocol/pystatsd]
# calls in requirements not used elsewhere, and
# the only upside seems to be support of "sets"

# See docs/stats.md for discussion of how statistics
# to name and organize statistics, the expected values
# for environment variables etc!!!

DEBUG = False
TAGS = False                    # get from env?? graphite >= 1.1.0 tags

logger = logging.getLogger(__name__)

def _getenv(var):
    """
    get an MC_STATSD_ environment variable, return None if not set
    (using MC_STATSD_  prefix to avoid preference to any packages naming)
    """
    v2 = f"MC_STATSD_{var}"
    val = os.environ.get(v2)
    if val:
        return val

    logger.warning(f"{v2} not set: not sending stats")
    return None


class Stats:
    """
    hide protocol and library being used for statistics
    """

    _instance = None

    @classmethod
    def init(cls, component):
        """
        called from main program
        """
        if cls._instance:
            raise Exception(f"Stats.init called twice: {component}/{cls._instance.component}")
        cls._instance = cls(component)
        return cls._instance


    @classmethod
    def get(cls):
        """
        called from non-main modules
        """
        if not cls._instance:
            raise Exception("Stats.init not called")
        return cls._instance


    def __init__(self, component):
        self.statsd = self.host = self.prefix = None
        self.component = component

        host = _getenv('HOST')
        if not host:
            return

        prefix = _getenv('PREFIX')
        if not prefix:
            return

        logger.info(f"sending stats to {host} with prefix {prefix}")

        # _connect (below) expects both or neither to be set:
        self.host = host
        self.prefix = prefix


    def _connect(self):
        if self.statsd or not self.host:
            return

        prefix = f"{self.prefix}.{self.component}"
        try:
            self.statsd = statsd.StatsdClient(self.host, prefix=prefix)
        except:
            pass

    def _name(self, name, labels=[]):
        """
        return a statsd suitable variable for name (may contain dots)
        and labels (in the prometheus sense), a list of [name,value] pairs.

        Sorts by dimension name to ensure consistent ordering.

        This MAY turn out to be a pain if you want to slice
        a chart based on one dimension (if that happens,
        add a no_sort argument to "inc" and "gauge", to pass here?
        """
        if labels:
            if TAGS: # graphite 1.1 tags
                # https://graphite.readthedocs.io/en/latest/tags.html#tags
                slabels = ';'.join([f"{name}={val}" for name, val in
                                    sorted(labels)])
                name = f"{name};{slabels}"
            else: # pre-1.1 graphite (or netdata?): no support for tags:
                slabels = '.'.join([f"{name}_{val}" for name, val in
                                    sorted(labels)])
                name = f"{name}.{slabels}"
        if DEBUG:
            print("name", name)
        return name

    def incr(self, name, value=1, labels=[]):
        """
        Increment a counter
        (something that never decreases, like an odometer)

        Please use the convention that counter names end in "s".
        """
        if not self.statsd:
            self._connect()

        if self.statsd:
            try:
                self.statsd.incr(self._name(name, labels), value)
            except:
                self.statsd = None

    def gauge(self, name, value, labels=[]):
        """
        Indicate value of a gauge
        (something that goes up and down, like a thermometer or speedometer)
        """
        if not self.statsd:
            self._connect()

        if self.statsd:
            try:
                self.statsd.gauge(self._name(name, labels), value)
            except:
                self.statsd = None


if __name__ == '__main__':
    s = Stats.init('foo')
    s2 = Stats.get()
    assert s is s2
    s.incr('requests')
    s.gauge('bar', 33.33, labels=(('y', 2), ('x', 1)))
