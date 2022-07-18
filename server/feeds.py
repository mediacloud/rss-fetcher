import logging
from typing import List, Dict
from fastapi import APIRouter
from sqlalchemy import select

from fetcher.database import Session
from server.util import api_method
from fetcher.database.models import FetchEvent

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/feeds",
    tags=["feeds"],
)


@router.get("/{feed_id}/history")
@api_method
def stories_fetched_counts(feed_id: int) -> List[Dict]:
    session = Session()
    query = select(FetchEvent).where(FetchEvent.feed_id == feed_id)
    fetch_events = session.execute(query).scalars().all()
    return [fe.as_dict() for fe in fetch_events]
