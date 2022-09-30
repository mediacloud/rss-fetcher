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

DEBUG = True

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
        self.statsd = None
        self.component = component

        host = _getenv('HOST')
        if not host:
            return

        prefix = _getenv('PREFIX')
        if not prefix:
            return

        self.statsd = statsd.StatsdClient(host, prefix=f"{prefix}.{component}")


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
        if self.statsd:
            # XXX handle error & re-create statsd?
            self.statsd.incr(self._name(name, labels), value)

    def gauge(self, name, value, labels=[]):
        """
        Indicate value of a gauge
        (something that goes up and down, like a thermometer or speedometer)
        """
        if self.statsd:
            # XXX handle error & re-create statsd?
            self.statsd.gauge(self._name(name, labels), value)

if __name__ == '__main__':
    s = Stats.init('foo')
    s2 = Stats.get()
    assert s is s2
    s.incr('requests')
    s.gauge('bar', 33.33, labels=(('y', 2), ('x', 1)))
