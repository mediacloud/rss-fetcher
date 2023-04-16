"""
HeadHunter: finds work for Workers.
(A more P.C. term might be Recruiter)

feeds must be ready in database, and be issuable according to all
scoreboards.

not super-efficient [O(n^3)]!!
"""

import logging
import time
from typing import Any, Dict, List, Optional, TypedDict, Union

# PyPI
from sqlalchemy import func, select, or_, over, update

# app:
from fetcher.database import Session, SessionType
from fetcher.database.models import Feed, utc
from fetcher.scoreboard import ScoreBoard
from fetcher.stats import Stats

logger = logging.getLogger(__name__)

# used as indices to Item and HeadHunter.scoreboards[]
SCOREBOARDS = ['sources_id', 'fqdn']

ScoreBoardsDict = Dict[str, ScoreBoard]

# how often to query DB for ready entries
DB_READY_SEC = 60

# ready items to return: if too small could return ONLY unissuable
# feeds.  more than can be fetched in DB_READY_SEC wastes effort,
# *AND* the current algorithm is O(n^2 - n) in the WORST case
# (lots of unissuable feeds)!!!
DB_READY_LIMIT = 1000

ITEM_COLS = [Feed.id, Feed.sources_id, Feed.url,
             Feed.last_fetch_attempt, Feed.last_fetch_success]

# passed as JSON from Manager to Worker


class Item(TypedDict):
    id: int
    sources_id: int
    url: str
    # calculated:
    fqdn: str


# these belong as Feed static methods; XXX FIXME after sqlalchemy 2.x upgrade
def _where_active(q):
    return q.where(Feed.active.is_(True),
                   Feed.system_enabled.is_(True))


def _where_ready(q):
    now = utc()
    return q.where(Feed.queued.is_(False),
                   or_(Feed.next_fetch_attempt <= now,
                       Feed.next_fetch_attempt.is_(None)))


def ready_feeds(session: SessionType) -> int:
    return int(
        session.scalar(
            _where_ready(
                _where_active(
                    select(func.count())))))


def running_feeds(session: SessionType) -> int:
    return int(
        session.scalar(select(func.count())
                       .where(Feed.queued.is_(True))))


def fqdn(url: str) -> Optional[str]:
    """hopefully faster than any formal URL parser."""
    try:
        items = url.split('/', 3)
        domain_portno = items[2].split(':')
        return domain_portno[0]
    except BaseException:                     # malformed URL
        return None             # special cased for ScoreBoard


class HeadHunter:
    """
    finds work for Workers.
    perhaps subclass into ListHeadHunter and DBHeadHunter?
    (and don't report stats in ListHeadHunter??)
    """

    def __init__(self) -> None:
        self.stats = Stats.get()  # singleton

        # make all private?
        self.ready_list: List[Item] = []
        self.next_db_check = 0
        self.fixed = False      # fixed length (command line list)
        self.scoreboards: ScoreBoardsDict = {
            sb: ScoreBoard() for sb in SCOREBOARDS
        }

    def refill(self, feeds: Optional[List[int]] = None) -> None:
        """
        called with non-empty list with command line feed ids
        """
        self.stats.incr('hunter.refill')

        # start DB query
        q = _where_active(select(ITEM_COLS))

        if feeds:
            q = q.where(Feed.id.in_(feeds),
                        Feed.queued.is_(False))
            self.fixed = True
        else:
            q = _where_ready(q).limit(DB_READY_LIMIT)

        q = q.order_by(Feed.next_fetch_attempt.asc().nullsfirst())
        # add Feed.poll_minutes.asc().nullslast() to preference fast feeds??

        self.ready_list = []
        with Session() as session:
            self.get_ready(session)  # send stats

            for feed in session.execute(q):
                d = Item(id=feed.id, sources_id=feed.sources_id, url=feed.url,
                         # calculated:
                         fqdn=fqdn(feed.url))
                self.ready_list.append(d)
            self.on_hand_stats()

        # query DB no more than once a DB_INTERVAL
        # XXX this could result in idle time
        #    when there are DB entries that have ripened:
        #    to do better would require getting next_fetch_attempt
        #    from fetched feeds, and refetching at that time???

        # if nothing is returned (ready empty) will requery
        # at next wakeup.
        self.next_db_check = int(time.time() + DB_READY_SEC)

    def have_work(self) -> bool:
        # loop unless fixed list (command line) and now empty
        return not self.fixed or len(self.ready_list) > 0

    def on_hand(self) -> int:
        return len(self.ready_list)

    def check_stale(self):
        if time.time() > self.next_db_check:
            self.ready_list = []

    def find_work(self) -> Optional[Item]:
        blocked = 0

        def blocked_stats(stalled):
            self.stats.gauge('hunter.blocked', blocked)
            if stalled:
                self.stats.incr('hunter.stalled')

        if self.fixed:          # command line list of feeds
            if not self.ready_list:
                # log EOL?
                return None
        else:
            self.check_stale()  # may clear ready_list
            if not self.ready_list:
                self.refill()

        if self.ready_list:
            # print("ready", self.ready_list)

            # reported as gauge, so only last count counts (use timer?)
            for item in self.ready_list:
                for sbname in SCOREBOARDS:
                    sb = self.scoreboards[sbname]
                    if not sb.safe(item[sbname]):
                        # XXX counter??
                        logger.debug(f"  UNSAFE {sbname} {item[sbname]}")
                        blocked += 1
                        break   # check next item
                else:
                    # made it through the gauntlet.
                    # mark item as issued on all scoreboards:
                    for sbname in SCOREBOARDS:
                        sb = self.scoreboards[sbname]
                        logger.debug(f"  issue {sbname} {item[sbname]}")
                        sb.issue(item[sbname])
                    # print("find_work ->", item)
                    self.ready_list.remove(item)
                    self.on_hand_stats()  # report updated list length
                    blocked_stats(False)
                    return item
                # here when "break" executed for some scoreboard
                # (not safe to issue): continue to next item in ready list

        # here with empty ready list, or nothing issuable (stall)
        logger.debug(f"no issuable work: {self.on_hand()} on hand")
        blocked_stats(True)
        return None

    def ready_count(self) -> int:
        return len(self.ready_list)

    def completed(self, item: Item) -> None:
        """
        called when an issued item is no longer active
        """
        for sbname in SCOREBOARDS:
            sb = self.scoreboards[sbname]

            logger.debug(f"  completed {sbname} {item[sbname]}")
            sb.completed(item[sbname])

    def get_ready(self, session: SessionType) -> None:
        # XXX keep timer to avoid querying too often??
        self.stats.incr('hunter.get_ready')

        ready = ready_feeds(session)
        self.stats.gauge('db.ready', ready)
        # print("db.ready", ready)

        running = running_feeds(session)
        self.stats.gauge('db.running', running)
        # print("db.running", running)

    def on_hand_stats(self) -> None:
        self.stats.gauge('on_hand', x := self.on_hand())
        # print("on_hand", x)
