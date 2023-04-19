"""
Common data across /api areas

Since this file is imported by multiple "router" files,
it shouldn't import from any of them (should be strictly a leaf).
"""

from typing import List

from sqlalchemy.sql.elements import ColumnElement

from fetcher.database.models import Story


# list of Story columns to return from /api/{feeds,sources}/ID/stories:
STORY_COLUMNS = [
    Story.url,
    Story.feed_id,
    Story.published_at,
    Story.fetched_at,
    Story.domain,
    Story.title]

# default limit of stories to return from /api/{feeds,sources}/ID/stories:
STORY_LIMIT = 50

# order of stories to return from /api/{feeds,sources}/ID/stories:
STORY_ORDER = Story.fetched_at.desc()
