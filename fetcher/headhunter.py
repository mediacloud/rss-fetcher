"""
HeadHunter: finds work for Workers.

feeds must be ready in database, and be issuable according to all
scoreboards.

not super-efficient!!!
"""

import logging
import time
from typing import Any, List, Optional

# PyPI
from sqlalchemy import func, select, or_, over, update

# app:
from fetcher.database import Session
from fetcher.database.models import Feed, utc
from fetcher.scoreboard import ScoreBoard

logger = logging.getLogger(__name__)

# used as indices to "item" and HeadHunter.scoreboards
# (make named tuple w/: name, concurrency?)
SCOREBOARDS = ['sources_id', 'fqdn']

# how often to query DB for ready entries
DB_READY_SEC = 60

# ready items to return: if too small could return ONLY unissuable feeds.
# more than can be fetched in DB_READY_SEC wastes effort.
DB_READY_LIMIT = 1000

def fqdn(url):
    """hopefully faster than any formal URL parser"""
    try:
        items = url.split('/')
        dom_port = items[2].split(':')
        return dom_port[0]
    except:
        return None             # special cased for ScoreBoard

class HeadHunter:
    """
    finds work for Workers.
    perhaps subclass into ListHeadHunter?
    """
    def __init__(self):
        self.ready = []
        self.next_db_check = 0
        self.fixed = False      # fixed length (command line list)
        self.scoreboards = {sb: ScoreBoard() for sb in SCOREBOARDS}

    def reset(self, feeds: Optional[List[int]] = None):
        # start DB query
        # XXX want Feed._where_active
        q = select([Feed.id, Feed.sources_id, Feed.url])\
            .where(Feed.active.is_(True),
                   Feed.system_enabled.is_(True))

        if feeds:
            q = q.where(Feed.id.in_(feeds),
                        Feed.queued.is_(False))
            self.fixed = True
        else:
            # XXX move to Feed._where_ready??
            now = utc()
            q = q.where(Feed.queued.is_(False),
                        or_(Feed.next_fetch_attempt <= now,
                            Feed.next_fetch_attempt.is_(None)))\
                 .limit(DB_READY_LIMIT)

        # add Feed.poll_minutes.asc().nullslast() to preference fast feeds
        q = q.order_by(Feed.next_fetch_attempt.asc().nullsfirst())

        self.ready = []
        with Session() as session:
            for feed in session.execute(q):
                d = dict(feed)
                d['fqdn'] = fqdn(d['url'])
                self.ready.append(d)

        # query DB no more than once a DB_INTERVAL
        # XXX this could result in idle time
        #    when there are DB entries that have ripened:
        #    to do better would require getting next_fetch_attempt
        #    from fetched feeds, and refetching at that time???
        if self.ready:
            wait = DB_READY_SEC
        else:
            wait = 10           # XXX
        self.next_db_check = int(time.time() + wait)

    def have_work(self):
        # loop unless fixed list (command line) and now empty
        return not self.fixed or self.ready

    def find_work(self):        # XXX returns "item" make a defined Dict?
        if self.fixed:
            if not self.ready:
                # log EOL?
                return None
        elif not self.ready or time.time() > self.next_db_check:
            self.reset()

        if self.ready:
            print("ready", self.ready)
            for item in self.ready:
                for key, sb in self.scoreboards.items():
                    if not sb.safe(item[key]):
                        print("UNSAFE", key, item[key], "***")
                        break   # check next item
                else:
                    # made it through the gauntlet.
                    # mark item as issued on all scoreboards:
                    for key, sb in self.scoreboards.items():
                        print("issue", key, item[key])
                        sb.issue(item[key])
                    print("find_work ->", item)
                    self.ready.remove(item)
                    return item
                # here when "break" executed for some scoreboard
                # (not safe to issue): continue to next item in ready list

        # here with empty ready list, or nothing issuable
        logger.debug(f"no issuable work: {len(self.ready)} ready")
        return None

    def completed(self, item):
        """
        called when an issued item is no longer active
        """
        for key, sb in self.scoreboards.items():
            print("completed", key, item[key])
            sb.completed(item[key])

