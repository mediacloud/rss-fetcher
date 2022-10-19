import datetime as dt
from enum import Enum
import hashlib
from time import mktime
from typing import Any, Dict, List, Optional

# PyPI:
import mcmetadata.urls as urls
import mcmetadata.titles as titles
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, BigInteger, DateTime, String, Boolean, Integer, text

from fetcher.database.engine import engine
import fetcher.util as util

Base = declarative_base()


def _class_as_dict(obj) -> Dict[str, Any]:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def utc(seconds: float = 0.0) -> dt.datetime:
    """
    Return a UTC datetime with optional offset of `seconds` from current time
    """
    d = dt.datetime.utcnow()
    if seconds != 0.0:
        d += dt.timedelta(seconds=seconds)
    return d


class Feed(Base):
    __tablename__ = 'feeds'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sources_id = Column(BigInteger)
    name = Column(String)
    url = Column(String)
    active = Column(Boolean, nullable=False, server_default=text('true'))
    last_fetch_attempt = Column(DateTime)
    last_fetch_success = Column(DateTime)
    last_fetch_hash = Column(String)
    last_fetch_failures = Column(
        Integer,
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

    def __repr__(self) -> str:
        return f"<Feed id={self.id} name={self.name} sources_id={self.sources_id}>"

    def as_dict(self) -> Dict[str, Any]:
        return _class_as_dict(self)


class Story(Base):
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
    def recent_fetched_volume(limit: int = 30):
        today = dt.date.today()
        earliest_date = today - dt.timedelta(days=limit)
        query = "select fetched_at::date as day, count(1) as stories from stories " \
                f"where fetched_at <= '{today}'::DATE AND fetched_at >= '{earliest_date}'::DATE " \
                "group by 1 order by 1 DESC"
        return _run_query(query)

    @staticmethod
    def recent_published_volume(limit: int = 30) -> int:
        today = dt.date.today()
        earliest_date = today - dt.timedelta(days=limit)
        query = "select published_at::date as day, count(1) as stories from stories " \
                f"where published_at <= '{today}'::DATE AND published_at >= '{earliest_date}'::DATE " \
                "group by 1 order by 1 DESC"
        return _run_query(query)

    @staticmethod
    def from_rss_entry(feed_id: int, fetched_at: dt.datetime,
                       entry, media_name: str = None) -> 'Story':
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
            s.normalized_title = titles.normalize_title(s.title)
            s.normalized_title_hash = hashlib.md5(
                s.normalized_title.encode()).hexdigest()
        except AttributeError as _:
            s.title = None
            s.normalized_title = None
            s.normalized_title_hash = None
        s.fetched_at = fetched_at
        return s

    def as_dict(self) -> Dict[str, Any]:
        return _class_as_dict(self)


def _run_query(query: str) -> List:
    data = []
    with engine.begin() as connection:
        result = connection.execute(text(query))
        for row in result:
            data.append(row)
    return data


class FetchEvent(Base):
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
        # disabled due to excessive failures
        FETCH_FAILED_DISABLED = 'fetch_disabled'

    def __repr__(self) -> str:
        return f"<FetchEvent id={self.id}>"

    @staticmethod
    def from_info(feed_id: int, event: Event,
                  note: Optional[str] = None,
                  ts: Optional[dt.datetime] = None) -> FetchEvent:
        fe = FetchEvent()
        fe.feed_id = feed_id
        fe.event = event.name
        fe.note = note
        fe.created_at = ts or dt.datetime.utcnow()
        return fe

    def as_dict(self) -> Dict[str, Any]:
        return _class_as_dict(self)
