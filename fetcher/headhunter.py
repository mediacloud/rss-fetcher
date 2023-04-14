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

logger = logging.getLogger(__name__)

# used as indices to "item" and HeadHunter.scoreboards
# (make named tuple w/: name, concurrency?)
SCOREBOARDS = ['sources_id', 'fqdn']

ScoreBoardsDict = Dict[str, ScoreBoard]

# how often to query DB for ready entries
DB_READY_SEC = 60

# ready items to return: if too small could return ONLY unissuable
# feeds.  more than can be fetched in DB_READY_SEC wastes effort,
# *AND* the current algorithm is O(n^2 - n) in the WORST case
# (lots of unissuable feeds)!!!
DB_READY_LIMIT = 1000

ITEM_COLS = [Feed.id, Feed.sources_id, Feed.url]

Item = Dict[str, Union[int, str, Optional[str]]]

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

def fqdn(url: str) -> Optional[str]:
    """hopefully faster than any formal URL parser."""
    try:
        items = url.split('/', 3)
        domain_portno = items[2].split(':')
        return domain_portno[0]
    except:                     # malformed URL
        return None             # special cased for ScoreBoard


class HeadHunter:
    """
    finds work for Workers.
    perhaps subclass into ListHeadHunter?
    """
    def __init__(self) -> None:
        self.total_ready = 0

        # make all private?
        self.ready_list: List[Item] = []
        self.next_db_check = 0
        self.fixed = False      # fixed length (command line list)
        self.scoreboards: ScoreBoardsDict = {
            sb: ScoreBoard() for sb in SCOREBOARDS
        }

    def refill(self, feeds: Optional[List[int]]=None) -> None:
        # start DB query
        q = _where_active(select(ITEM_COLS))

        if feeds:
            q = q.where(Feed.id.in_(feeds),
                        Feed.queued.is_(False))
            self.fixed = True
        else:
            # XXX send "ready" count here????
            q = _where_ready(q).limit(DB_READY_LIMIT)

        # add Feed.poll_minutes.asc().nullslast() to preference fast feeds
        q = q.order_by(Feed.next_fetch_attempt.asc().nullsfirst())

        self.ready_list = []
        with Session() as session:
            self.get_ready(session)

            for feed in session.execute(q):
                d: Item = dict(feed)
                d['fqdn'] = fqdn(d['url'])  # mostly for aggregator urls!
                self.ready_list.append(d)

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

    def find_work(self) -> Optional[Item]:
        if self.fixed:          # command line list of feeds
            if not self.ready_list:
                # log EOL?
                return None
        elif not self.ready_list or time.time() > self.next_db_check:
            self.refill()

        if self.ready_list:
            # print("ready", self.ready_list)
            for item in self.ready_list:
                for key, sb in self.scoreboards.items():
                    if not sb.safe(item[key]):
                        # XXX counter??
                        logger.debug(f"  UNSAFE {key} {item[key]}")
                        break   # check next item
                else:
                    # made it through the gauntlet.
                    # mark item as issued on all scoreboards:
                    for key, sb in self.scoreboards.items():
                        logger.debug(f"  issue {key} {item[key]}")
                        sb.issue(item[key])
                    # print("find_work ->", item)
                    self.ready_list.remove(item)
                    self.total_ready -= 1  # XXX check >= 0?
                    return item
                # here when "break" executed for some scoreboard
                # (not safe to issue): continue to next item in ready list

        # here with empty ready list, or nothing issuable (stall)
        logger.debug(f"no issuable work: {len(self.ready_list)} ready")
        return None

    def ready_count(self) -> int:
        return len(self.ready_list)

    def completed(self, item: Item) -> None:
        """
        called when an issued item is no longer active
        """
        for key, sb in self.scoreboards.items():
            logger.debug(f"  completed {key} {item[key]}")
            sb.completed(item[key])

    def get_ready(self, session: SessionType) -> int:
        self.total_ready = ready_feeds(session)
        return self.total_ready
