import logging
from typing import Dict

from fastapi import APIRouter, Depends
from sqlalchemy import func

from fetcher.database import Session
from fetcher.database.models import Story

import server.auth as auth
from server.util import as_timeseries_data, api_method, TimeSeriesData

DEFAULT_DAYS = 30

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/stories",
    tags=["stories"],
)


@router.get("/fetched-by-day", dependencies=[Depends(auth.read_access)])
@api_method
def stories_fetched_counts() -> TimeSeriesData:
    return as_timeseries_data(
        [Story.recent_published_volume(limit=DEFAULT_DAYS)],
        ["stories"]
    )


@router.get("/published-by-day", dependencies=[Depends(auth.read_access)])
@api_method
def stories_published_counts() -> TimeSeriesData:
    return as_timeseries_data(
        [Story.recent_fetched_volume(limit=DEFAULT_DAYS)],
        ["stories"]
    )


@router.get("/by-source", dependencies=[Depends(auth.read_access)])
@api_method
def stories_by_source() -> Dict[str, object]:
    with Session() as session:
        counts = session.query(Story.sources_id, func.count(Story.id))\
                        .group_by(Story.sources_id).all()
        dates = session.query(func.max(Story.fetched_at),
                              func.min(Story.fetched_at)).one()
    return {'dates': dates, 'sources': list(counts)}
