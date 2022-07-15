import unittest

from fetcher.tasks import _fetch_rss_feed
import feedparser
from time import mktime
import datetime as dt
from fetcher.database.models import Story


class TestStory(unittest.TestCase):

    def test_from_rss_entry_bad_timezone_offset(self):
        # +16 is out of bounds for Python (valid is -12/+14)
        fake_feed = {
            'id': 123,
            'url': "http://wen.org.cn/modules/article/xml.php/rss"
        }
        response = _fetch_rss_feed(fake_feed)
        parsed_feed = feedparser.parse(response.content)
        assert len(parsed_feed.entries) > 0
        for entry in parsed_feed.entries:
            assert entry.published_parsed is not None
            s = Story.from_rss_entry(fake_feed['id'], dt.datetime.now(), entry)
            assert s.published_at == dt.datetime.fromtimestamp(mktime(entry.published_parsed))


if __name__ == "__main__":
    unittest.main()


