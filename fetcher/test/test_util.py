import unittest

from .. import util


class TestUrlUtil(unittest.TestCase):

    def test_relative_url(self):
        test_url = "https://observers.france24.com/en/20190826-mexico-african-migrants-trapped-protest-journey"
        assert util.is_absolute_url(test_url) is True
        test_url = "//observers.france24.com/en/20190826-mexico-african-migrants-trapped-protest-journey"
        assert util.is_absolute_url(test_url) is True
        test_url = "/en/20190826-mexico-african-migrants-trapped-protest-journey"
        assert util.is_absolute_url(test_url) is False


if __name__ == "__main__":
    unittest.main()
