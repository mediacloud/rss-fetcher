import datetime as dt
from enum import Enum
from typing import Any, Dict, Optional

# PyPI:
from sqlalchemy import (BigInteger, Boolean, Column, DateTime, Float, Index,
                        Integer, String, or_, select, text)
from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy.sql._typing import _ColumnsClauseArgument
from sqlalchemy.sql.selectable import Select


class Base(DeclarativeBase):
    __abstract__ = True

    def as_dict(self) -> Dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    def as_dict_public(self) -> Dict[str, Any]:
        """
        return dict with only public fields
        (default to everything).  Could use a class
        variable with a set to pick those to export.
        """
        return self.as_dict()


def utc(seconds: float = 0.0) -> dt.datetime:
    """
    Return a UTC datetime with optional offset of `seconds` from current time
    """
    d = dt.datetime.utcnow()
    if seconds != 0.0:
        d += dt.timedelta(seconds=seconds)
    return d


# The datetime of the start of each fetch  runis used in the following places:
# * Feed.last_fetch_{attempt,success}, .last_new_stories
# * FetchEvent.created_at for fetch run
# * Story.created_at for all new stories in feed
# * StoryRef.seen_at for all stories in feed

class Feed(Base):
    __tablename__ = 'feeds'

    id = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sources_id = mapped_column(BigInteger)
    name = mapped_column(String)
    url = mapped_column(String)
    active = mapped_column(
        Boolean,
        nullable=False,
        server_default=text('true'))
    last_fetch_attempt = mapped_column(DateTime)
    last_fetch_success = mapped_column(DateTime)
    last_fetch_hash = mapped_column(String)
    last_fetch_failures = mapped_column(
        Float,
        nullable=False,
        server_default=text('0'))
    created_at = mapped_column(DateTime)
    http_etag = mapped_column(String)  # "Entity Tag"
    http_last_modified = mapped_column(String)
    next_fetch_attempt = mapped_column(DateTime)

    # "queued" now means "currently being fetched"
    # and is set in the main() function of scripts/fetcher.py
    queued = mapped_column(
        Boolean,
        nullable=False,
        server_default=text('false'))
    system_enabled = mapped_column(
        Boolean,
        nullable=False,
        server_default=text('true'))
    # sy:updatePeriod/sy:updateFrequency
    update_minutes = mapped_column(Integer)
    http_304 = mapped_column(Boolean)        # sends HTTP 304 "Not Modified"
    system_status = mapped_column(String)
    last_new_stories = mapped_column(DateTime)
    rss_title = mapped_column(String)  # ONLY set from RSS feed title
    poll_minutes = mapped_column(Integer)  # poll period override
    # ^^^ _COULD_ be auto-adaptive (add bool adaptive(_poll)?)

    __table_args__ = (
        Index('feeds_system_enabled', 'system_enabled'),
        Index('feeds_sources_id', 'sources_id'),
        Index('feeds_next_fetch_attempt', 'last_fetch_attempt'),
        Index('feeds_active', 'active'),
    )

    def __repr__(self) -> str:
        return f"<Feed id={self.id} name={self.name} sources_id={self.sources_id}>"

    @staticmethod
    def select_where_active(
            *entities: _ColumnsClauseArgument[Any]) -> Select[Any]:
        """
        Helper for defining queries.
        Should be the ONE place where the "active" test is coded.
        """
        return select(*entities).where(Feed.active.is_(True),
                                       Feed.system_enabled.is_(True))

    @classmethod
    def select_where_ready(cls,
                           *entities: _ColumnsClauseArgument[Any]) -> Select[Any]:
        """
        Helper for defining queries.
        Should be the ONE place where the "ready" test is coded.
        """

        now = utc()
        return cls.select_where_active(*entities)\
                  .where(Feed.queued.is_(False),
                         or_(Feed.next_fetch_attempt <= now,
                             Feed.next_fetch_attempt.is_(None)))


class Story(Base):
    __tablename__ = 'stories'

    id = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    feed_id = mapped_column(BigInteger)
    sources_id = mapped_column(BigInteger)
    url = mapped_column(String)
    normalized_url = mapped_column(String)
    guid = mapped_column(String)
    published_at = mapped_column(DateTime)
    fetched_at = mapped_column(DateTime)
    domain = mapped_column(String)
    title = mapped_column(String)
    normalized_title = mapped_column(String)
    normalized_title_hash = mapped_column(String)

    __table_args__ = (
        Index('unique_story_url', 'normalized_url', unique=True),
        Index('unique_story_title', 'normalized_title_hash', 'sources_id'),
        Index('stories_sources_id', 'sources_id'),
        Index('stories_published_at', 'published_at'),
        Index('stories_fetched_at', 'fetched_at'),
        Index('stories_feed_id', 'feed_id'),
        Index('stories_domain', 'domain'),
    )

    def __repr__(self) -> str:
        return f"<Story id={self.id}>"


class StoryRef(Base):
    """
    Record the last time a story was seen from a feed.
    With the goal of only expiring stories that are no longer present in any feeds.

    Multiple entries may exist for the same story.

    Updated (replaced due to MVCC) each time story still in feed (or returned same hash)
      so entry kept small.
    """
    __tablename__ = 'story_refs'

    # story_id first so can be used for db_archive (see below)
    story_id = mapped_column(BigInteger, primary_key=True, nullable=False)
    feed_id = mapped_column(BigInteger, primary_key=True, nullable=False)

    # MUST match the Story.last_fetch_success time at which the story was last seen
    # in order to update the row if the feed document hash hasn't changed.
    seen_at = mapped_column(DateTime)

    __table_args__ = (
        # primary key can be used for finding Stories by story_id
        # (used in db_archive.py to expire refs)
        Index('story_refs_seen_at', 'seen_at'),  # for expiration
        Index('story_refs_feed_id', 'feed_id'),  # for static feed doc
    )


class FetchEvent(Base):
    __tablename__ = 'fetch_events'

    id = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    feed_id = mapped_column(BigInteger)
    event = mapped_column(String)      # Event enum
    note = mapped_column(String)
    created_at = mapped_column(DateTime)

    class Event(Enum):
        QUEUED = 'queued'
        FETCH_FAILED = 'fetch_failed'
        FETCH_SUCCEEDED = 'fetch_succeeded'
        # disabled due to excessive failures:
        FETCH_FAILED_DISABLED = 'fetch_disabled'

    __table_args__ = (
        Index('fetch_events_feeds_id', 'feed_id'),
        Index('fetch_events_created_at', 'created_at'),
    )

    def __repr__(self) -> str:
        return f"<FetchEvent id={self.id}>"

    @staticmethod
    def from_info(feed_id: int, event: Event,
                  created_at: Optional[dt.datetime],
                  note: Optional[str] = None) -> 'FetchEvent':
        fe = FetchEvent()
        fe.feed_id = feed_id
        fe.event = event.value  # shorter, lower case
        fe.note = note
        fe.created_at = created_at
        return fe


class Property(Base):
    __tablename__ = 'properties'

    # see property.py for section, key values:
    section = Column(String, primary_key=True, nullable=False)
    key = Column(String, primary_key=True, nullable=False)
    value = Column(String)

    # NOTE: no additional indices: primary key is section + key
    # __table_args__ = (
    # )
