from sqlalchemy.orm import declarative_base, Session
from sqlalchemy import Column, BigInteger, DateTime, String, Boolean, Integer, text
import datetime as dt
from typing import List
import hashlib

from fetcher import engine
from dateutil.parser import parse
import mcmetadata.urls as urls
import mcmetadata.titles as titles

Base = declarative_base()


class Feed(Base):
    __tablename__ = 'feeds'

    id = Column(BigInteger, primary_key=True)
    mc_feeds_id = Column(BigInteger)
    mc_media_id = Column(BigInteger)
    name = Column(String)
    url = Column(String)
    active = Column(Boolean)
    type = Column(String)
    last_fetch_attempt = Column(DateTime)
    last_fetch_success = Column(DateTime)
    last_fetch_hash = Column(String)
    last_fetch_failures = Column(Integer)
    import_round = Column(Integer)

    def __repr__(self):
        return '<Feed id={} name={} mc_media_id={} mc_feeds_id={}>'.format(
            self.id, self.name, self.mc_media_id, self.mc_feeds_id)


class Story(Base):
    __tablename__ = 'stories'

    id = Column(BigInteger, primary_key=True)
    feed_id = Column(BigInteger)
    media_id = Column(BigInteger)
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

    def title_already_exists(self, day_window: int = 7):
        # for deduplication - check if this title hash exists in the last 7 days, if so it is a dupe
        matches = Story.find_by_normalized_title_hash(self.normalized_title_hash, self.media_id, day_window)
        return len(matches) > 0

    @staticmethod
    def find_by_normalized_title_hash(normalized_title_hash: str, media_id: int, limit: int = 7):
        earliest_date = dt.date.today() - dt.timedelta(days=limit)
        query = "select count(1) from stories " \
                "where (published_at >= '{}'::DATE) AND (normalized_title_hash = '{}')"\
            .format(earliest_date, normalized_title_hash)
        return _run_query(query)

    @staticmethod
    def recent_fetched_volume(limit: int = 30):
        earliest_date = dt.date.today() - dt.timedelta(days=limit)
        query = "select fetched_at::date as day, count(1) as stories from stories " \
                "where fetched_at >= '{}'::DATE " \
                "group by 1 order by 1 DESC"\
            .format(earliest_date)
        return _run_query(query)

    @staticmethod
    def recent_published_volume(limit: int = 30):
        earliest_date = dt.date.today() - dt.timedelta(days=limit)
        query = "select published_at::date as day, count(1) as stories from stories " \
                "where published_at >= '{}'::DATE " \
                "group by 1 order by 1 DESC"\
            .format(earliest_date)
        return _run_query(query)

    @staticmethod
    def from_rss_entry(feed_id: int, fetched_at: dt.datetime, entry, media_name: str = None):
        s = Story()
        s.feed_id = feed_id
        try:
            s.url = entry.link
            s.url = urls.normalize_url(entry.link)
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
            s.published_at = parse(entry.published)
        except Exception as _:  # likely to be an unknown string format - let the pipeline guess it from HTML later
            s.published_at = None
        try:
            s.title = entry.title
            s.normalized_title = titles.normalize_title(entry.title, media_name)
            s.normalized_title_hash = hashlib.md5(s.normalized_title).hexdigest()
        except AttributeError as _:
            s.title = None
            s.normalized_title = None
            s.normalized_title_hash = None
        s.fetched_at = fetched_at
        return s


def _run_query(query: str) -> List:
    data = []
    with engine.begin() as connection:
        result = connection.execute(text(query))
        for row in result:
            data.append(row)
    return data
