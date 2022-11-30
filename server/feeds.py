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
