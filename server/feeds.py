import logging
from typing import Dict, List, Optional
from fastapi import APIRouter

from fetcher.database import Session
from server.util import api_method
from fetcher.database.models import Feed, FetchEvent

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/feeds",
    tags=["feeds"],
)


@router.get("/{feed_id}/history")
@api_method
def get_feed_history(feed_id: int) -> List[Dict]:
    with Session() as session:
        # XXX limit rows returned (by date or count)??
        fetch_events = session.query(FetchEvent)\
                              .filter(FetchEvent.feed_id == feed_id)\
                              .order_by(Feed.id.desc())\
                              .all()
        return [fe.as_dict() for fe in fetch_events]


@router.get("/{feed_id}")
@api_method
def get_feed(feed_id: int) -> Optional[Dict]:
    with Session() as session:
        feed: Optional[Feed] = session.get(Feed, feed_id)
        if feed:
            return feed.as_dict()
        else:
            return None
