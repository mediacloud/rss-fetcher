from urllib.parse import urlparse


def is_absolute_url(url):
    # https://stackoverflow.com/questions/8357098/how-can-i-check-if-a-url-is-absolute-using-python
    return bool(urlparse(url).netloc)
