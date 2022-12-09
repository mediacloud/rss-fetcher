import logging
from typing import Optional, TYPE_CHECKING

from fastapi import APIRouter, Depends

from fetcher.database import models

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
        [models.Story.recent_published_volume(limit=DEFAULT_DAYS)],
        ["stories"]
    )


@router.get("/published-by-day", dependencies=[Depends(auth.read_access)])
@api_method
def stories_published_counts() -> TimeSeriesData:
    return as_timeseries_data(
        [models.Story.recent_fetched_volume(limit=DEFAULT_DAYS)],
        ["stories"]
    )
