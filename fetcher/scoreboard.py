"""
Scheduling scoreboards for HeadHunter

The term scoreboard was first used in Seymour Cray's CDC 6600
(the first supercomputer) to safely issue instructions out of order:
https://en.wikipedia.org/wiki/Scoreboarding

Possible efficiency improvements:

Keep track of dependencies in each scoreboard item so that newly
issuable items can be checked as soon as a blocking condition clears.
Would likely require scoreboard.py to keep persistent Items (rather
than throwing them all away on each "refill").  Paranoia regarding
entries that disappear could be avoided by doing Feed query and sanity
check before passing Feed Item to Worker??

Expose lowest "next_start" value so that fetcher can sleep
appropriately (now sleeping RSS_FETCH_FEED_SECS so that newly cleared
items can be issued at minimum interval)
"""

# Python
import logging
import time
from typing import Any, Dict

# app:
from fetcher.config import conf

RSS_FETCH_FEED_SECS = conf.RSS_FETCH_FEED_SECS


class SBItem:
    """
    Score Board Item
    """

    def __init__(self) -> None:
        self.current = 0
        # XXX keep queue of blocked feeds (would add complexity)
        self.next_start = 0     # next time safe to issue
        # XXX implement full rate limiting???
        #   https://levelup.gitconnected.com/implement-rate-limiting-in-python-d4f86b09259f
        #   https://gist.github.com/daanzu/d34fa69e0094a3f5be6a
        #   https://builtin.com/software-engineering-perspectives/rate-limiter
        #   PyPI ratelimiter: https://github.com/RazerM/ratelimiter/


SBIndex = Any


class ScoreBoard:
    """
    Scheduling score board for HeadHunter

    NOTE!  Starting simple:

    Does not (yet) keep track of dependencies
    that keep a feed from being issued.
    This makes the "find next feed" operation O(n^2)
    (times the number of scoreboards!)

    Wants to be a Generic? Subclasses can have different index types.
    Currently: SBIndex used instead of bare "Any"

    *OR* could always index by "str"

    NOTE! index of None means the value was unavailable
    (fqdn failed), so skip testing.
    """

    # XXX take delay (from last issue? last completion???) max rate???
    def __init__(self, concurrency: int = 1):
        self.concurrency = concurrency
        self.board: Dict[SBIndex, SBItem] = {}

    def safe(self, index: SBIndex) -> bool:
        """
        index can be any attribute of feed: sources_id, fqdn, etc.
        """
        if index is None:
            return True

        entry = self.board.get(index)
        if entry:
            if entry.current >= self.concurrency:
                # XXX counter?
                return False
            if time.time() < entry.next_start:
                # XXX counter?
                return False
        return True

    def issue(self, index: SBIndex) -> None:
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
        item.next_start = time.time() + RSS_FETCH_FEED_SECS

    def completed(self, index: SBIndex) -> None:
        """
        Mark a feed as completed.
        """
        if index is None:
            return

        assert index in self.board
        sbitem = self.board[index]
        sbitem.current -= 1
        assert sbitem.current >= 0
        # XXX if current == 0, could delete item (save memory, cost time)
        # XXX if any saved dependencies, mark as unblocked?
