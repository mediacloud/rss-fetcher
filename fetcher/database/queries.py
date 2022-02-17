import datetime as dt
from typing import List, Dict
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from dateutil.parser import parse

from fetcher import engine
from fetcher.database.models import Feed, Story
import fetcher.domains as domains

Session = sessionmaker(bind=engine)


def feeds_to_check(limit: int) -> List[Dict]:
    query = "select id, url, last_fetch_hash from feeds " \
            "where ((last_fetch_attempt is NULL) or (last_fetch_attempt <= NOW() - INTERVAL '1 DAY'))" \
            "  and type='syndicated' and active=true " \
            "order by last_fetch_attempt ASC, id DESC " \
            "LIMIT {}" \
            .format(limit)
    return _run_query(query)


def process_stories_fetched_on(day: dt.date) -> List[Dict]:
    query = "select id, url, guid, published_at from stories where fetched_at::date = '{}'::date".format(day.strftime("%Y-%m-%d"))
    data = []
    with engine.begin() as connection:
        result = connection.execute(text(query))
        for row in result:
            yield dict(row)
    return data


def update_last_fetch_attempt(feed_id: int, the_time: dt.datetime):
    session = Session()
    f = session.query(Feed).get(feed_id)
    f.last_fetch_attempt = the_time
    session.commit()


def update_last_fetch_success_hash(feed_id: int, the_time: dt.datetime, hash: str):
    session = Session()
    f = session.query(Feed).get(feed_id)
    f.last_fetch_success = the_time
    f.last_fetch_hash = hash
    session.commit()


def save_story_from_feed_entry(feed_id: int, fetched_at: dt.datetime, entry):
    s = Story()
    s.feed_id = feed_id
    try:
        s.url = entry.link
    except AttributeError as ae:
        s.url = None
    try:
        s.guid = entry.id
    except AttributeError as ae:
        s.guid = None
    s.published_at = parse(entry.published)
    s.fetched_at = fetched_at
    s.domain = domains.canonical_mediacloud_domain(entry.link)
    session = Session()
    session.add(s)
    session.commit()


def _run_query(query: str) -> List:
    data = []
    with engine.begin() as connection:
        result = connection.execute(text(query))
        for row in result:
            data.append(dict(row))
    return data


