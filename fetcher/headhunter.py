"""
HeadHunter: finds work for Workers.
(A more P.C. term might be Recruiter)
Not sophisticated enough to be called a Scheduler!!

Terminology used is that of CPU instruction scheduling:
"issue": to start execution
"blocked" and "unsafe": cannot currently be issued
"scoreboard": machinery that tracks issued feeds

not super-efficient [at least O(n^3)]?!

Possible improvements:

Use row_number by source_id in refill to limit the maximum number of
feeds from one source in the ready_list (ie; constrain "n" to small
values)

Expose the next time a feed could be issued based on delay (so
fetcher.py can sleep an appropriate amount of time).

Keep Items between "refills" so that scoreboard.py can track
dependencies!!!

See scoreboard.py for more!
"""

import logging
import time
from typing import Any, Dict, List, NamedTuple, Optional, Union

# PyPI
from sqlalchemy import func, select, over, update

# app:
from fetcher.config import conf
from fetcher.database import Session, SessionType
from fetcher.database.models import Feed
from fetcher.scoreboard import ScoreBoard
from fetcher.stats import Stats

# read at startup, for logging
RSS_FETCH_FEED_CONCURRENCY = conf.RSS_FETCH_FEED_CONCURRENCY
RSS_FETCH_FEED_SECS = conf.RSS_FETCH_FEED_SECS

logger = logging.getLogger(__name__)

# used as HeadHunter.scoreboards[] index, and Item attr
SCOREBOARDS = ('sources_id', 'fqdn')

# only legal indices are members of SCOREBOARD tuple (above)
# TypedDict requires access by string lit only!
ScoreBoardsDict = Dict[str, ScoreBoard]

# how often to refill ready_list (query DB for ready entries)
DB_READY_SEC = 60

DB_READY_LIMIT = conf.RSS_FETCH_READY_LIMIT

ITEM_COL_NAMES = ['id', 'sources_id', 'url']
ITEM_COLS = [getattr(Feed, col) for col in ITEM_COL_NAMES]


class Item(NamedTuple):
    # from ITEM_COLS:
    id: int
    sources_id: int
    url: str
    # calculated (for scoreboards):
    fqdn: Optional[str]         # None if bad URL


def ready_feeds(session: SessionType) -> int:
    return int(session.scalar(Feed.select_where_ready(func.count())))


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
            sb: ScoreBoard(concurrency=RSS_FETCH_FEED_CONCURRENCY,
                           interval=float(RSS_FETCH_FEED_SECS))
            for sb in SCOREBOARDS
        }

    def refill(self, feeds: Optional[List[int]] = None) -> None:
        """
        called with non-empty list with command line feed ids
        """
        self.stats.incr('hunter.refill')

        # start DB query
        nfa = Feed.next_fetch_attempt.asc().nullsfirst()
        if feeds:
            q = Feed.select_where_active(*ITEM_COLS)\
                    .where(Feed.id.in_(feeds),
                           Feed.queued.is_(False))
            q = q.order_by(nfa)
            self.fixed = True
        else:
            rank_col = func.row_number()\
                           .over(partition_by=Feed.sources_id, order_by=nfa)\
                           .label('rank')

            # XXX include next_fetch_attempt for outer query ORDER BY?
            #   for more accurate ordereding between feeds? does it matter???
            subq = Feed.select_where_ready(*ITEM_COLS, rank_col)
            # print("subq", subq)
            subq_cols = [getattr(subq.c, col) for col in ITEM_COL_NAMES]
            max_rank = (DB_READY_SEC//RSS_FETCH_FEED_SECS *
                        RSS_FETCH_FEED_CONCURRENCY)
            q = select(*subq_cols, subq.c.rank)\
                .where(subq.c.rank <= max_rank)\
                .order_by(subq.c.rank)\
                .limit(DB_READY_LIMIT)
            # print("q", q)
        self.ready_list = []
        with Session() as session:
            self.get_ready(session)  # send stats

            for feed in session.execute(q):
                # NOTE! columns here needs to be in FEED_COL_NAMES!!!
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

        # if nothing is returned (ready empty) will re-query
        # at next wakeup.
        self.next_db_check = int(time.time() + DB_READY_SEC)

    def have_work(self) -> bool:
        # loop unless fixed list (command line) and now empty
        return not self.fixed or len(self.ready_list) > 0

    def on_hand(self) -> int:
        return len(self.ready_list)

    def check_stale(self) -> None:
        if time.time() > self.next_db_check:
            self.stats.incr('hunter.stale')
            self.ready_list = []

    def find_work(self) -> Optional[Item]:
        blocked = 0
        self.stats.incr('hunter.find_work')

        def blocked_stats(stalled: bool) -> None:
            self.stats.gauge('hunter.blocked', blocked)
            if stalled:
                self.stats.incr('hunter.stalled')

        if self.fixed:          # command line list of feeds
            if not self.ready_list:
                # log EOL?
                return None
        else:
            self.check_stale()  # may clear ready_list
            # except when stale_check clear list, more likely
            # to have non-empty list with stalled entries
            if not self.ready_list:
                self.refill()

        if self.ready_list:
            # print("ready", self.ready_list)

            # reported as gauge, so only last count counts (use timer?)
            for item in self.ready_list:
                for sbname in SCOREBOARDS:
                    self.debug_item("checking", item)
                    sb = self.scoreboards[sbname]
                    itemval = getattr(item, sbname)
                    if not sb.safe(itemval):
                        logger.debug(f"  UNSAFE {sbname} {itemval}")
                        blocked += 1
                        break   # check next item
                else:
                    # made it through the gauntlet.
                    # mark item as issued on all scoreboards:
                    self.debug_item("issue", item)
                    for sbname in SCOREBOARDS:
                        sb = self.scoreboards[sbname]
                        itemval = getattr(item, sbname)
                        logger.debug(f"  issue {sbname} {itemval}")
                        sb.issue(itemval)
                    # print("find_work ->", item)
                    self.ready_list.remove(item)
                    self.on_hand_stats()  # report updated list length
                    blocked_stats(False)  # not stalled
                    return item
                # here when "break" executed for some scoreboard
                # (not safe to issue): continue to next item in ready list

        # here with empty ready list, or nothing issuable (stall)
        logger.debug(f"no issuable work: {self.on_hand()} on hand")
        blocked_stats(True)     # stalled
        return None

    def ready_count(self) -> int:
        return len(self.ready_list)

    def completed(self, item: Item) -> None:
        """
        called when an issued item is no longer active
        """
        self.debug_item("completed", item)
        for sbname in SCOREBOARDS:
            sb = self.scoreboards[sbname]
            itemval = getattr(item, sbname)
            logger.debug(f"  completed {sbname} {itemval}")
            sb.completed(itemval)

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

    def debug_item(self, what: str, item: Item) -> None:
        logger.debug(f"{what} {item.id} {item.sources_id} {item.fqdn}")
