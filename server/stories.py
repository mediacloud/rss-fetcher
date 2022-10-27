import logging
from typing import Optional, TYPE_CHECKING
from flask import send_from_directory
from fastapi import APIRouter
if TYPE_CHECKING:  # pragma: no cover
    from flask.wrappers import Response

from server.util import as_timeseries_data, api_method, TimeSeriesData
from fetcher.database import models

DEFAULT_DAYS = 30

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/stories",
    tags=["stories"],
)


@router.get("/fetched-by-day")
@api_method
def stories_fetched_counts(days: Optional[int] = None) -> TimeSeriesData:
    return as_timeseries_data(
        [models.Story.recent_published_volume(limit=(days or DEFAULT_DAYS))],
        ["stories"]
    )


@router.get("/published-by-day")
@api_method
def stories_published_counts(days: Optional[int] = None) -> TimeSeriesData:
    return as_timeseries_data(
        [models.Story.recent_fetched_volume(limit=(days or DEFAULT_DAYS))],
        ["stories"]
    )

