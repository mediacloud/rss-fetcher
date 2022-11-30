import logging
from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import select

from fetcher.database import Session
from fetcher.database.models import Feed

import server.auth as auth
from server.util import api_method

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/sources",
    tags=["sources"],
)


@router.get("/{sources_id}/feeds", dependencies=[Depends(auth.read_access)])
@api_method
def sources_feeds(sources_id: int) -> List[Dict]:
    with Session() as session:
        feeds = session.query(Feed)\
                       .filter(Feed.sources_id == sources_id)\
                       .all()
        return [feed.as_dict_public() for feed in feeds]
