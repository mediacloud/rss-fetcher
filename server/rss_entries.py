import datetime as dt
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from fetcher.database.asyncio import AsyncSession

import server.auth as auth
from server.util import api_method

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/rss_entries",
)


@router.get("/{story_id}", dependencies=[Depends(auth.read_access)])
@api_method
async def get_rss_entries(
        story_id: int,
        _limit: Optional[int] = Query(default=1,
                                      description="max rows to return",
                                      ge=1)) -> List[Dict]:
    logger.info("rss_entries id %d limit %d", story_id, _limit)

    query = """
        select s.id, s.url, s.published_at, s.domain, s.title, s.feed_id, s.sources_id, f.url as feed_url
        from stories s
        left join feeds f
        on s.feed_id = f.id
        where s.url is not null and s.id >= :id
        order by s.id asc
        limit :limit
    """
    async with AsyncSession() as session:
        results = await session.execute(text(query), {"id": story_id, "limit": _limit})
        rows = [story._asdict() for story in results]
        logger.info("rss_entries returning %d rows", len(rows))
        return rows
