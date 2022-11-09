import logging
from typing import List, Dict
from fastapi import APIRouter
from sqlalchemy import select

from fetcher.database import Session
from server.util import api_method
from fetcher.database.models import Feed

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/sources",
    tags=["sources"],
)


@router.get("/{sources_id}/feeds")
@api_method
def sources_feeds(sources_id: int) -> List[Dict]:
    with Session() as session:
        feeds = session.query(Feed)\
                       .filter(Feed.sources_id == sources_id)\
                       .all()
        return [feed.as_dict_public() for feed in feeds]
