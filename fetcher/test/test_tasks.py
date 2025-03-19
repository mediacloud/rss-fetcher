import datetime as dt
import os
import unittest

import feedparser
import psycopg2
import psycopg2.errors
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import fetcher.database
import fetcher.database.models as models
import fetcher.path
import fetcher.tasks as tasks

fixture_dir = os.path.join(
    fetcher.path.BASE_DIR,
    'fetcher',
    'test',
    'fixtures')


class DBTest(unittest.TestCase):

    def setUp(self) -> None:
        # create a database
        try:
            conn = psycopg2.connect(database='postgres', host='127.0.0.1')
            conn.autocommit = True
            cursor = conn.cursor()
            sql = '''CREATE database test_rss_fetcher'''
            cursor.execute(sql)
            cursor.close()
        except psycopg2.errors.DuplicateDatabase:
            pass
        self._engine = create_engine(
            "postgresql:///test_rss_fetcher", pool_size=5)
        self._Session = sessionmaker(bind=self._engine)
        # create an empty in-memory database
        models.Base.metadata.bind = self._engine
        models.Base.metadata.create_all()

    def tearDown(self) -> None:
        try:
            self._engine.dispose()
            conn = psycopg2.connect(database='postgres', host='127.0.0.1')
            conn.autocommit = True
            cursor = conn.cursor()
            sql = '''DROP database test_rss_fetcher WITH (FORCE)'''
            cursor.execute(sql)
            conn.close()
        except psycopg2.OperationalError:
            pass


class TestTableCreation(DBTest):

    def test_tables_created(self):
        # make sure the stories table is there and empty, awaiting test data
        with self._Session() as session:
            total_stories = session.query(models.Story.id).count()
            assert total_stories == 0


class TestSaveFetchEvent(DBTest):

    def test_save_fetch_event(self):
        with self._Session() as session:
            tasks.save_fetch_event(
                session, 1, models.FetchEvent.EVENT_FETCH_FAILED, "fake")
            total_events = session.query(models.FetchEvent.id).count()
            assert total_events == 1

    def test_save_fetch_events(self):
        with self._Session() as session:
            tasks.save_fetch_event(
                session, 1, models.FetchEvent.EVENT_FETCH_FAILED, "fake")
            tasks.save_fetch_event(
                session, 1, models.FetchEvent.EVENT_FETCH_FAILED, "fake")
            total_events = session.query(models.FetchEvent.id).count()
            assert total_events == 2


class TestFetchFeedContent(DBTest):

    def _create_feed(self):
        f = models.Feed()
        f.sources_id = 1
        f.name = "Media Cloud"
        f.url = "https://mediacloud.org"
        f.active = True
        f.last_fetch_attempt = None
        f.last_fetch_success = None
        f.last_fetch_hash = None
        f.last_fetch_failures = 0
        f.import_round = 1
        with self._Session() as session:
            session.add(f)
            session.commit()
        with self._Session() as session:
            total_feeds = session.query(models.Feed.id).count()
            assert total_feeds == 1

    def test_invalid_rss_parse(self):
        # an invalid RSS should create a fetch_event failure and increment last
        # failed counts
        self._create_feed()
        with self._Session() as session:
            tasks._parse_feed(session, 1, "some garbage")
        with self._Session() as session:
            total_fetch_events = session.query(models.FetchEvent.id).count()
            assert total_fetch_events == 1
        with self._Session() as session:
            stmt = select(models.Feed).where(models.Feed.id == 1)
            results = session.execute(stmt)
            for f in results.scalars():
                assert f.last_fetch_failures == 1

    def test_invalid_rss(self):
        # an invalid RSS should create a fetch_event failure and increment last
        # failed counts
        self._create_feed()
        with self._Session() as session:
            tasks.fetch_feed_content(session, dt.datetime.now(), dict(
                id=1,
                url="https://example.com",
                last_fetch_hash="abcdef"
            ))
        with self._Session() as session:
            stmt = select(models.Feed).where(models.Feed.id == 1)
            results = session.execute(stmt)
            for f in results.scalars():
                assert f.last_fetch_failures == 1


class TestSaveStoriesFromFeed(DBTest):

    def test_real_korean_times(self):
        with open(os.path.join(fixture_dir, 'real-korean-times.rss')) as f:
            content = f.read()
        parsed_feed = feedparser.parse(content)
        assert len(parsed_feed.entries) == 195
        with self._Session() as session:
            feed = dict(id=1, sources_id=1, name='cnn')
            tasks.save_stories_from_feed(
                session, dt.datetime.now(), feed, parsed_feed)
            total_stories = session.query(models.Story.id).count()
            assert total_stories == 195
            total_fetch_events = session.query(models.FetchEvent.id).count()
            assert total_fetch_events == 1

    def test_real_cnn(self):
        # make sure stories get saved
        with open(os.path.join(fixture_dir, 'real-cnn.rss')) as f:
            content = f.read()
        parsed_feed = feedparser.parse(content)
        assert len(parsed_feed.entries) == 69
        with self._Session() as session:
            feed = dict(id=1, sources_id=1, name='cnn')
            tasks.save_stories_from_feed(
                session, dt.datetime.now(), feed, parsed_feed)
            total_stories = session.query(models.Story.id).count()
            assert total_stories == 69
            total_fetch_events = session.query(models.FetchEvent.id).count()
            assert total_fetch_events == 1

    def test_duplicates_cnn(self):
        # run a feed twice and make sure that the stories from it are only
        # saved once
        with open(os.path.join(fixture_dir, 'real-cnn.rss')) as f:
            content = f.read()
        parsed_feed = feedparser.parse(content)
        assert len(parsed_feed.entries) == 69
        with self._Session() as session:
            feed = dict(id=1, sources_id=1, name='cnn')
            saved, dups, skipped = tasks.save_stories_from_feed(
                session, dt.datetime.now(), feed, parsed_feed)
            assert saved == 69
            assert skipped == 0
            total_stories = session.query(models.Story.id).count()
            assert total_stories == 69
            total_fetch_events = session.query(models.FetchEvent.id).count()
            assert total_fetch_events == 1
            # now try to import the same ones again
        with self._Session() as session:
            saved, dups, skipped = tasks.save_stories_from_feed(
                session, dt.datetime.now(), feed, parsed_feed)
            assert saved == 0
            assert dups == 69
            total_stories = session.query(models.Story.id).count()
            assert total_stories == 69
            total_fetch_events = session.query(models.FetchEvent.id).count()
            assert total_fetch_events == 2


class TestHelpers(unittest.TestCase):

    def test_fetch_rss_feed(self):
        url = "http://rss.cnn.com/rss/cnn_topstories.rss"
        response = tasks._fetch_rss_feed({'url': url})
        assert response.status_code == 200
        assert len(response.content) > 0


if __name__ == "__main__":
    unittest.main()
