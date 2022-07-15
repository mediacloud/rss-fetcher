import unittest

from fetcher.tasks import _fetch_rss_feed


class TestTasks(unittest.TestCase):

    def test_fetch_rss_feed(self):
        url = "http://rss.cnn.com/rss/cnn_topstories.rss"
        response = _fetch_rss_feed({'url': url})
        assert response.status_code == 200
        assert len(response.content) > 0


if __name__ == "__main__":
    unittest.main()
