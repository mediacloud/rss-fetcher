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

    def test_clean_str(self):
        # an actual title our system ran into
        s = "Golden Curls -“Say Love– \x00\x00\x00\x00\x00\x00\x00”\x00“What’Golden Curls -“Say Love”"
        cleaned_str = util.clean_str(s)
        assert cleaned_str == 'Golden Curls -“Say Love– ”“What’Golden Curls -“Say Love”'


if __name__ == "__main__":
    unittest.main()
