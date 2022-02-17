from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, BigInteger, DateTime, String, Boolean

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

    def __repr__(self):
        return '<Story id={}>'.format(self.id)
