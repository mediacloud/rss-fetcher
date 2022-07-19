from urllib.parse import urlparse


def is_absolute_url(url):
    # https://stackoverflow.com/questions/8357098/how-can-i-check-if-a-url-is-absolute-using-python
    return bool(urlparse(url).netloc)


def clean_str(s: str) -> str:
    # Some titles had null characters in them, which can't be saved to XML
    return s.replace("\x00", "")
