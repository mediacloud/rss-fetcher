import datetime as dt
import logging
from typing import Any, Dict, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, func, select
from sqlalchemy.orm.attributes import InstrumentedAttribute

import server.auth as auth
from fetcher.config import conf
from fetcher.database.asyncio import AsyncSession
from fetcher.database.models import Story
from server.util import TimeSeriesData, api_method

DEFAULT_DAYS = 30
TOP_SOURCE_DAYS = conf.TOP_SOURCE_DAYS

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/stories",
    tags=["stories"],
)


async def _recent_volume(date_var: InstrumentedAttribute[dt.date],
                         limit: int = DEFAULT_DAYS) -> TimeSeriesData:
    today = dt.datetime.utcnow().date()
    earliest_date = today - dt.timedelta(days=limit)

    async with AsyncSession() as session:
        # for MySQL use func.date(date_var)??
        date = date_var.cast(Date)
        results = await session.execute(
            select(date.label('date'),
                   func.count(Story.id).label('n'))
            .where(date_var <= today, date_var >= earliest_date)
            .group_by(date)
            .order_by(date.desc())
        )
        return [
            {'date': row.date, 'count': row.n, 'type': 'stories'}
            for row in results
        ]


@router.get("/fetched-by-day", dependencies=[Depends(auth.read_access)])
@api_method
async def stories_fetched_counts() -> TimeSeriesData:
    return await _recent_volume(Story.fetched_at)


@router.get("/published-by-day", dependencies=[Depends(auth.read_access)])
@api_method
async def stories_published_counts() -> TimeSeriesData:
    return await _recent_volume(Story.published_at)


@router.get("/by-source", dependencies=[Depends(auth.read_access)])
@api_method
async def stories_by_source() -> Dict[str, Any]:
    async with AsyncSession() as session:
        counts = await session.execute(
            select(Story.sources_id.label('sources_id'),
                   func.count(Story.id).label('count'))
            .group_by(Story.sources_id)
        )
        dates = await session.execute(
            select(func.max(Story.fetched_at).label('max'),
                   func.min(Story.fetched_at).label('min'))
        )
        row = dates.one()
        min = row.min.timestamp()
        max = row.max.timestamp()
        SECONDS_PER_DAY = 26 * 60 * 60

        # Return time span of data separately, and let the caller deal
        # with scaling; this call is slow as-is, and floating point
        # encode/decode is slow, and would yield a larger message,
        # and json decode is also slow.
        return {
            'days': (max - min) / SECONDS_PER_DAY,
            'sources': [count._asdict() for count in counts]
        }


# new 2026-04-07
@router.get("/count", dependencies=[Depends(auth.read_access)])
@api_method
async def count(
        column: Literal["domain", "feed_id", "sources_id"] = Query(
            default="domain", description="name of column to aggregate by"),
        days: int = Query(default=TOP_SOURCE_DAYS,
                          description="number of days to total",
                          ge=1),
        _limit: int = Query(default=10,
                            description="max rows to return",
                            ge=1)
) -> list[dict[str, Any]]:
    """
    Query to get top total stories by "source" for recent days to help
    find flood sources.

    With "column=domain" (the default) helps find source of
    "top-domain" alerts generated from stories.top-domain.{sum,avg}
    system gauges.
    """

    # copied from rss-fetcher-stats.py:report_top_domain_stories:
    start = dt.datetime.utcnow() - dt.timedelta(days=days)

    # NOTE! _COULD_ return/group-by multiple columns
    # as story-indexer pipeview API does!
    col_obj = getattr(Story, column).label('column')
    count = func.count(col_obj)
    query = (
        select(col_obj, count)
        .where(Story.fetched_at >= start)
        .group_by(col_obj)
        .order_by(count.desc())
        .limit(_limit)
    )
    async with AsyncSession() as session:
        results = await session.execute(query)
    return [
        {column: row.column, 'count': row.count}
        for row in results
    ]
