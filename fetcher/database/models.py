import datetime as dt
from enum import Enum
import hashlib
from time import mktime
from typing import Any, Dict, List, Optional

# PyPI:
from feedparser.util import FeedParserDict
import mcmetadata.urls as urls
import mcmetadata.titles as titles
from sqlalchemy import Column, BigInteger, DateTime, String, Boolean, Integer, text, Float
# SQLAlchemy moves this to sqlalchemy.orm, but available type hints only
# has it old location:
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm.query import Query

from fetcher.database.engine import engine
import fetcher.util as util

Base = declarative_base()


class MyBase(Base):
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


class Feed(MyBase):
    __tablename__ = 'feeds'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sources_id = Column(BigInteger)
    name = Column(String)       # ONLY set from mcweb feeds.name field
    url = Column(String)
    active = Column(Boolean, nullable=False, server_default=text('true'))
    last_fetch_attempt = Column(DateTime)
    last_fetch_success = Column(DateTime)
    last_fetch_hash = Column(String)
    last_fetch_failures = Column(
        Float,
        nullable=False,
        server_default=text('0'))
    created_at = Column(DateTime)
    http_etag = Column(String)  # "Entity Tag"
    http_last_modified = Column(String)
    next_fetch_attempt = Column(DateTime)
    queued = Column(Boolean, nullable=False, server_default=text('false'))
    system_enabled = Column(
        Boolean,
        nullable=False,
        server_default=text('true'))
    update_minutes = Column(Integer)  # sy:updatePeriod/sy:updateFrequency
    http_304 = Column(Boolean)        # sends HTTP 304 "Not Modified"
    system_status = Column(String)
    last_new_stories = Column(DateTime)
    rss_title = Column(String)  # ONLY set from RSS feed title
    poll_minutes = Column(Integer)  # poll period override
    # ^^^ _COULD_ be auto-adaptive (add bool adaptive(_poll)?)

    def __repr__(self) -> str:
        return f"<Feed id={self.id} name={self.name} sources_id={self.sources_id}>"

    @staticmethod
    def _active_filter(q: Query) -> Query:
        """
        Helper for defining queries:
        filter a feeds query to return only active feeds.
        This is MEANT to be the only place to define this policy.
        """
        return q.filter(Feed.active.is_(True),
                        Feed.system_enabled.is_(True))


class Story(MyBase):
    __tablename__ = 'stories'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    feed_id = Column(BigInteger)
    sources_id = Column(BigInteger)
    url = Column(String)
    normalized_url = Column(String)
    guid = Column(String)
    published_at = Column(DateTime)
    fetched_at = Column(DateTime)
    domain = Column(String)
    title = Column(String)
    normalized_title = Column(String)
    normalized_title_hash = Column(String)

    def __repr__(self) -> str:
        return f"<Story id={self.id}>"

    @staticmethod
    def recent_fetched_volume(limit: int) -> List[Any]:
        today = dt.date.today()
        earliest_date = today - dt.timedelta(days=limit)
        query = "select fetched_at::date as day, count(1) as stories from stories " \
                f"where fetched_at <= '{today}'::DATE AND fetched_at >= '{earliest_date}'::DATE " \
                "group by 1 order by 1 DESC"
        return _run_query(query)

    @staticmethod
    def recent_published_volume(limit: int) -> List[Any]:
        today = dt.date.today()
        earliest_date = today - dt.timedelta(days=limit)
        query = "select published_at::date as day, count(1) as stories from stories " \
                f"where published_at <= '{today}'::DATE AND published_at >= '{earliest_date}'::DATE " \
                "group by 1 order by 1 DESC"
        return _run_query(query)

    @staticmethod
    def from_rss_entry(feed_id: int,  # type: ignore[no-any-unimported]
                       fetched_at: dt.datetime,
                       entry: FeedParserDict,
                       media_name: Optional[str] = None) -> 'Story':
        s = Story()
        s.feed_id = feed_id
        try:
            s.url = entry.link
            s.normalized_url = urls.normalize_url(entry.link)
            s.domain = urls.canonical_domain(entry.link)
        except AttributeError as _:
            s.url = None
            s.normalized_url = None
            s.domain = None
        try:
            s.guid = entry.id
        except AttributeError as _:
            s.guid = None
        try:
            time_struct = entry.published_parsed
            s.published_at = dt.datetime.fromtimestamp(mktime(time_struct))
        except Exception as _:  # likely to be an unknown string format - let the pipeline guess it from HTML later
            s.published_at = None
        try:
            # code prior to this should have checked for title uniqueness biz
            # logic
            # make sure we can save it in the DB by removing NULL chars and
            # such
            s.title = util.clean_str(entry.title)
            s.normalized_title = titles.normalize_title(s.title or "")
            s.normalized_title_hash = hashlib.md5(
                s.normalized_title.encode()).hexdigest()
        except AttributeError as _:
            s.title = None
            s.normalized_title = None
            s.normalized_title_hash = None
        s.fetched_at = fetched_at
        return s


def _run_query(query: str) -> List[Any]:
    data = []
    with engine.begin() as connection:
        result = connection.execute(text(query))
        # PLB would "return list(result)" work?
        for row in result:
            data.append(row)
    return data


class FetchEvent(MyBase):
    __tablename__ = 'fetch_events'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    feed_id = Column(BigInteger)
    event = Column(String)      # Event enum
    note = Column(String)
    created_at = Column(DateTime)

    class Event(Enum):
        QUEUED = 'queued'
        FETCH_FAILED = 'fetch_failed'
        FETCH_SUCCEEDED = 'fetch_succeeded'
        # disabled due to excessive failures:
        FETCH_FAILED_DISABLED = 'fetch_disabled'

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


class Property(MyBase):
    __tablename__ = 'properties'

    # see property.py for section, key values:
    section = Column(String, primary_key=True, nullable=False)
    key = Column(String, primary_key=True, nullable=False)
    value = Column(String)
