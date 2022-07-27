import unittest
import datetime as dt
import fetcher.rss.rsswriter as rsswriter
from email.utils import formatdate


class TestEscape(unittest.TestCase):

    def test_escape_chars(self):
        escaped = rsswriter._escape("some & <html> /\\")
        assert escaped == "some &amp; &lt;html&gt; /\\"

    def test_nothing_to_escape(self):
        test_str = "some normal test's"
        escaped = rsswriter._escape(test_str)
        assert escaped == test_str

    def test_html_escaped(self):
        escaped = rsswriter._escape("this is &quot; using")
        assert escaped == "this is \" using"


class TestAddItem(unittest.TestCase):

    def test_basic(self):
        now = dt.datetime.now()
        now_str = formatdate(now.timestamp())
        content = rsswriter.add_item(None, "myurl", now, "domain.com", "my title")
        assert content == "<item><link>myurl</link><pubDate>{}</pubDate><domain>domain.com</domain><title>my title</title></item>".format(now_str)

    def test_no_title(self):
        now = dt.datetime.now()
        now_str = formatdate(now.timestamp())
        content = rsswriter.add_item(None, "myurl", now, "domain.com", None)
        assert content == "<item><link>myurl</link><pubDate>{}</pubDate><domain>domain.com</domain><title></title></item>".format(now_str)


if __name__ == "__main__":
    unittest.main()
