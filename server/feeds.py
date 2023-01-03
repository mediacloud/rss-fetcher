import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from fetcher.database import Session
from fetcher.database.models import Feed, FetchEvent, Story

import server.auth as auth
from server.util import api_method
from server.common import STORY_COLUMNS, STORY_LIMIT, STORY_ORDER


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/feeds",
    tags=["feeds"],
)


@router.post("/{feed_id}/fetch-soon",
             dependencies=[Depends(auth.write_access)])
@api_method
def fetch_feed_soon(feed_id: int) -> int:
    """
    Mark feed to be fetched ASAP.
    Only contends with feeds that have never been attempted
    (and others that come thru this path).

    Clears last_fetch_failures and sets system_enabled to TRUE.

    Returns 1 on success, 0 if feed does not exist, or already queued.
    """

    # MAYBE move scripts.queue_feeds.queue_feeds() into its own file
    # and call it here?  Need to lock row and make sure not queued first??
    # NOTE! isnot(True) may not work in DB's w/o bool type (eg MySQL)??
    with Session() as session:
        count = session.query(Feed)\
                       .filter(Feed.id == feed_id,
                               Feed.queued.isnot(True))\
                       .update({'next_fetch_attempt': None,  # ASAP
                                'last_fetch_failures': 0,
                                'system_enabled': True})
        session.commit()
    return int(count)


@router.get("/{feed_id}/history", dependencies=[Depends(auth.read_access)])
@api_method
def get_feed_history(feed_id: int,
                     limit: Optional[int] = Query(
                         default=None,
                         description="max rows to return",
                         gt=1)) -> List[Dict]:
    with Session() as session:
        query = session.query(FetchEvent)\
                       .filter(FetchEvent.feed_id == feed_id)

        if limit:
            # if limit supplied return N most recent
            query = query.order_by(FetchEvent.id.desc())\
                         .limit(limit)

        return [event.as_dict_public() for event in query.all()]


@router.get("/{feed_id}", dependencies=[Depends(auth.read_access)])
@api_method
def get_feed(feed_id: int) -> Optional[Dict]:
    with Session() as session:
        feed: Optional[Feed] = session.get(Feed, feed_id)
        if feed:
            return feed.as_dict_public()
        else:
            return None


# maybe take limit as a query parameter _limit=N??
@router.get("/{feed_id}/stories",
            dependencies=[Depends(auth.write_access)])
@api_method
def fetch_feed_stories(feed_id: int) -> List[Dict[str, Any]]:
    """
    return story details.
    see also sources.fetch_source_stories
    """
    query = (select(STORY_COLUMNS)
             .where(Story.feed_id == feed_id)
             .order_by(STORY_ORDER)
             .limit(STORY_LIMIT))
    with Session() as session:
        return [s._asdict() for s in session.execute(query)]
