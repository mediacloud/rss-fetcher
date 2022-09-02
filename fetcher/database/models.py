from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, BigInteger, DateTime, String, Boolean, Integer, text
import datetime as dt
from time import mktime
from typing import List
import hashlib
from numbers import Real        # allows int or float

from fetcher import engine
import fetcher.util as util
import mcmetadata.urls as urls
import mcmetadata.titles as titles

Base = declarative_base()


def _class_as_dict(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def utc(seconds : Real = 0.0):
    """
    Return a UTC datetime with optional offset of `seconds` from current time
    """
    d = dt.datetime.utcnow() # or dt.datetime.now(dt.timezone.utc) ??
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
    last_fetch_failures = Column(Integer, nullable=False, server_default=text('0'))
    created_at = Column(DateTime)
    http_etag = Column(String)  # "Entity Tag"
    http_last_modified = Column(String)
    next_fetch_attempt = Column(DateTime)
    queued = Column(Boolean, nullable=False, server_default=text('false'))
    system_enabled = Column(Boolean, nullable=False, server_default=text('true'))
    update_minutes = Column(Integer) # sy:updatePeriod/sy:updateFrequency

    def __repr__(self):
        return '<Feed id={} name={} sources_id={}>'.format(
            self.id, self.name, self.sources_id)

    def as_dict(self):
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

    def __repr__(self):
        return '<Story id={}>'.format(self.id)

    @staticmethod
    def recent_fetched_volume(limit: int = 30):
        earliest_date = dt.date.today() - dt.timedelta(days=limit)
        query = "select fetched_at::date as day, count(1) as stories from stories " \
                "where fetched_at <= '{}'::DATE AND fetched_at >= '{}'::DATE " \
                "group by 1 order by 1 DESC"\
            .format(dt.date.today(), earliest_date)
        return _run_query(query)

    @staticmethod
    def recent_published_volume(limit: int = 30):
        earliest_date = dt.date.today() - dt.timedelta(days=limit)
        query = "select published_at::date as day, count(1) as stories from stories " \
                "where published_at <= '{}'::DATE AND published_at >= '{}'::DATE " \
                "group by 1 order by 1 DESC"\
            .format(dt.date.today(), earliest_date)
        return _run_query(query)

    @staticmethod
    def from_rss_entry(feed_id: int, fetched_at: dt.datetime, entry, media_name: str = None):
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
            # code prior to this should have checked for title uniqueness biz logic
            s.title = util.clean_str(entry.title)  # make sure we can save it in the DB by removing NULL chars and such
            s.normalized_title = titles.normalize_title(s.title)
            s.normalized_title_hash = hashlib.md5(s.normalized_title.encode()).hexdigest()
        except AttributeError as _:
            s.title = None
            s.normalized_title = None
            s.normalized_title_hash = None
        s.fetched_at = fetched_at
        return s

    def as_dict(self):
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

    EVENT_QUEUED = 'queued'
    EVENT_FETCH_FAILED = 'fetch_failed'
    EVENT_FETCH_SUCCEEDED = 'fetch_succeeded'
    EVENT_FETCH_FAILED_DISABLED = 'fetch_disabled' # disabled due to excessive failures

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    feed_id = Column(BigInteger)
    event = Column(String)
    note = Column(String)
    created_at = Column(DateTime)

    def __repr__(self):
        return '<FetchEvent id={}>'.format(self.id)

    @staticmethod
    def from_info(feed_id: int, event: str, note: str = None):
        fe = FetchEvent()
        fe.feed_id = feed_id
        fe.event = event
        fe.note = note
        fe.created_at = dt.datetime.now()
        return fe

    def as_dict(self):
        return _class_as_dict(self)
