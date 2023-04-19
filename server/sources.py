import logging
from typing import Any, Dict, List, Optional
import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import cast, func, select, text, update, Date
import sqlalchemy.sql.functions as f
from sqlalchemy.orm.attributes import InstrumentedAttribute

from fetcher.database.asyncio import AsyncSession
from fetcher.database.models import Feed, Story

import server.auth as auth
from server.util import api_method
from server.common import STORY_COLUMNS, STORY_LIMIT, STORY_ORDER

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/sources",
    tags=["sources"],
)


@router.get("/{sources_id}/feeds", dependencies=[Depends(auth.read_access)])
@api_method
async def sources_feeds(sources_id: int) -> List[Dict]:
    async with AsyncSession() as session:
        feeds = await session.execute(
            select(Feed)
            .where(Feed.sources_id == sources_id))
        # was .as_dict_public, but fails w/ async?
        return [feed._asdict() for feed in feeds]


@router.post("/{sources_id}/fetch-soon",
             dependencies=[Depends(auth.write_access)])
@api_method
async def fetch_source_feeds_soon(sources_id: int) -> int:
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
    async with AsyncSession() as session:
        # returns closed CursorResult:
        result = await session.execute(
            update(Feed)
            .where(Feed.sources_id == sources_id,
                   Feed.queued.op("is not")(True))
            .values(next_fetch_attempt=soon)
        )
        count = result.rowcount  # type: ignore[attr-defined]
        await session.commit()
    return int(count)

# maybe take limit as a query parameter _limit=N??


@router.get("/{sources_id}/stories",
            dependencies=[Depends(auth.write_access)])
@api_method
async def fetch_source_stories(sources_id: int) -> List[Dict[str, Any]]:
    """
    return story details.
    see also feeds.fetch_feed_stories
    """
    query = (select(*STORY_COLUMNS)
             .where(Story.sources_id == sources_id)
             .order_by(STORY_ORDER)
             .limit(STORY_LIMIT))
    async with AsyncSession() as session:
        return [s._asdict() for s in await session.execute(query)]


async def _sources_stories_by_day(sources_id: int, column: InstrumentedAttribute) -> List[Dict[str, Any]]:
    """
    helper for fetch_source_stories_{fetched,published}_by_day.

    NOTE! labels match return from
        /api/stories/{fetched,published}-by-day whose dicts contain
        type: "stories";
    could add them in query or by hand-made dicts in comprehension
    """
    day = cast(column, Date).label('day')
    query = (select(day, f.count().label('stories'))
             .where(Story.sources_id == sources_id)
             .group_by(day)
             .order_by(day))
    async with AsyncSession() as session:
        return [row._asdict()
                for row in await session.execute(query)]


@router.get("/{sources_id}/stories/fetched-by-day",
            dependencies=[Depends(auth.write_access)])
@api_method
async def fetch_source_stories_fetched_by_day(
        sources_id: int) -> List[Dict[str, Any]]:
    """
    named like /api/stories/fetched-by-day;
    return count of stories by fetched_by day.
    """
    return await _sources_stories_by_day(sources_id, Story.fetched_at)


@router.get("/{sources_id}/stories/published-by-day",
            dependencies=[Depends(auth.write_access)])
@api_method
async def fetch_source_stories_published_by_day(
        sources_id: int) -> List[Dict[str, Any]]:
    """
    named like /api/stories/fetched-by-day;
    return count of stories by fetched_by day.
    """
    return await _sources_stories_by_day(sources_id, Story.published_at)
