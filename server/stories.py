import datetime as dt
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, Date
from sqlalchemy.orm.attributes import InstrumentedAttribute

from fetcher.database.asyncio import AsyncSession
from fetcher.database.models import Story

import server.auth as auth
from server.util import api_method, TimeSeriesData

DEFAULT_DAYS = 30

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
