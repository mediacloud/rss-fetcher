import logging
from typing import Union
from flask import send_from_directory
from fastapi import Query, APIRouter

from util import as_timeseries_data, api_method
from fetcher.database import models

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/stories",
    tags=["stories"],
)


@router.get("/fetched-by-day")
@api_method
def stories_fetched_counts(days: Union[int, None] = None):
    return as_timeseries_data([models.Story.recent_published_volume(limit=days)], ["stories"])


@router.get("/published-by-day")
@api_method
def stories_published_counts(days: Union[int, None] = None):
    return as_timeseries_data([models.Story.recent_fetched_volume(limit=days)], ["stories"])


@router.get("/api/rss/<filename>")
def rss(filename: str = Query(..., description="The full name of the daily RSS file you want to retrieve")):
    return send_from_directory(directory='static', path='rss', filename=filename)

