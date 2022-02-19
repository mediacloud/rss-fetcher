from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, BigInteger, DateTime, String, Boolean
import datetime as dt

from dateutil.parser import parse
import fetcher.domains as domains

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

    def __repr__(self):
        return '<Feed id={} name={} mc_media_id={} mc_feeds_id={}>'.format(
            self.id, self.name, self.mc_media_id, self.mc_feeds_id)


class Story(Base):
    __tablename__ = 'stories'

    id = Column(BigInteger, primary_key=True)
    feed_id = Column(BigInteger)
    url = Column(String)
    guid = Column(String)
    published_at = Column(DateTime)
    fetched_at = Column(DateTime)
    domain = Column(String)
    title = Column(String)

    def __repr__(self):
        return '<Story id={}>'.format(self.id)

    @staticmethod
    def from_rss_entry(feed_id: int, fetched_at: dt.datetime, entry):
        s = Story()
        s.feed_id = feed_id
        try:
            s.url = entry.link
            s.domain = domains.canonical_mediacloud_domain(entry.link)
        except AttributeError as _:
            s.url = None
            s.domain = None
        try:
            s.guid = entry.id
        except AttributeError as _:
            s.guid = None
        try:
            s.published_at = parse(entry.published)
        except AttributeError as _:
            s.published_at = None
        try:
            s.title = entry.title
        except AttributeError as _:
            s.title = None
        s.fetched_at = fetched_at
        return s
