from urllib.parse import urlparse
from typing import Optional


def is_absolute_url(url: str) -> bool:
    # https://stackoverflow.com/questions/8357098/how-can-i-check-if-a-url-is-absolute-using-python
    try:
        return bool(urlparse(url).netloc)
    except ValueError:
        # could be an invalid UPv6 URL
        return False


def clean_str(s: Optional[str]) -> Optional[str]:
    # Some titles had null characters in them, which can't be saved to XML
    if s is None:
        return ''
    return s.replace("\x00", "")
