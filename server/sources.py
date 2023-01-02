import logging
from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
import sqlalchemy.sql.functions as f

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


@router.post("/{sources_id}/fetch-soon",
             dependencies=[Depends(auth.write_access)])
@api_method
def fetch_source_feeds_soon(sources_id: int) -> int:
    """
    Mark feeds associated with source to be fetched "soon".
    But to avoid clumping all of the feeds together, tries
    to spread them out.

    Does NOT re-enable disabled feeds.

    Returns number of feeds updated.
    """

    # spread out feeds
    hours = 3                   # get from environment??
    bucket_minutes = 5
    buckets = hours * 60 // bucket_minutes

    # bucket_minutes as a database INTERVAL (PG specific)
    binterval = text(f"'{bucket_minutes} minutes'::INTERVAL")

    # PG specific:
    utcnow = text("TIMEZONE('utc', CURRENT_TIMESTAMP)")

    # get a bucket number:
    # bucket = f.random() * buckets
    bucket = Feed.id % buckets

    soon = utcnow + bucket * binterval

    # NOTE! isnot(True) may not work in DB's w/o bool type (eg MySQL)??
    with Session() as session:
        count = session.query(Feed)\
                       .filter(Feed.sources_id == sources_id,
                               Feed.queued.isnot(True))\
                       .update({'next_fetch_attempt': soon})
        session.commit()
    return int(count)
