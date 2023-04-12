"""
Scheduling score boards for HeadHunter

    The term Score Board was first used in the first
    supercomputer, Seymour Cray's CDC 6600 to control
    out of order issue of instructions:
    https://en.wikipedia.org/wiki/Scoreboarding
"""

from typing import Any, Dict

# currently limited to concurrency control ONLY

class SBItem:
    """
    Score Board Item
    """
    def __init__(self):
        self.current = 0
        # XXX keep queue of blocked feeds?
        # XXX keep time of last issue? last completion??
        # XXX implement rate limiting?
        #   https://levelup.gitconnected.com/implement-rate-limiting-in-python-d4f86b09259f
        #   https://gist.github.com/daanzu/d34fa69e0094a3f5be6a
        #   https://builtin.com/software-engineering-perspectives/rate-limiter
        #   PyPI ratelimiter: https://github.com/RazerM/ratelimiter/

SBIndex = Any
class ScoreBoard:
    """
    Scheduling score board for HeadHunter

    NOTE!  Does not (yet) keep track of dependencies
    that keep a feed from being issued.

    Written as a class so that issue can be controlled on multiple
    dimensions (sources_id, domain, FQDN,...)  [tho could just
    "qualify" index with string prefixes "srcid:"]

    Wants to be a Generic? Subclasses can have different index types.
    Currently: SBIndex used instead of bare "Any"

    *OR* could always index by "str"
    """

    # XXX take delay (from last issue? last completion???) max rate???
    def __init__(self, concurrency: int = 1):
        self.concurrency = concurrency
        self.board: Dict[SBIndex, SBItem] = {}

    def safe(self, index: SBIndex):
        """
        see if safe to issue feed named by "index".
        Index can be any attribute of feed: sources_id, fqdn, etc.
        """
        if index is None:
            return True

        if index in self.board:
            # XXX check rate/timers!!!!
            # XXX if not currently safe, add dependency
            return self.board[index].current < self.concurrency
        else:
            return True

    def issue(self, index: SBIndex):
        """
        Mark a feed as issued (started).
        Only call after "safe" in all dimensions.
        """
        if index is None:
            return

        assert self.safe(index)  # TEMP paranoia

        item = self.board.get(index)
        if not item:
            item = self.board[index] = SBItem()
        item.current += 1

    def completed(self, index: SBIndex):
        """
        Mark a feed as completed.
        """
        if index is None:
            return

        assert index in self.board
        sbitem = self.board[index]
        sbitem.current -= 1
        assert sbitem.current >= 0
        # XXX if any saved dependencies, mark as unblocked?
