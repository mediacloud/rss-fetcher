import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from fetcher.database import Session
from fetcher.database.models import Feed, FetchEvent

import server.auth as auth
from server.util import api_method

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/feeds",
    tags=["feeds"],
)


@router.post("/{feed_id}/fetch-soon",
             dependencies=[Depends(auth.write_access)])
@api_method
def post_feed_fetch_soon(feed_id: int) -> int:
    """
    Mark feed to be fetched ASAP.
    Only contends with feeds that have never been attempted
    (and others that come thru this path).

    Originally created sepate "reset-errors" and "fetch-soon",
    (this does both).
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
