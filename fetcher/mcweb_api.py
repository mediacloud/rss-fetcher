"""
Interface to mcweb API for rss-fetcher
Phil Budne, December 2022
(adapted from web-search/mcweb/backend/sources/rss_fetcher_api.py)
"""

import logging
import os
from typing import Any, Dict, Optional

# PyPI
import requests.sessions

from fetcher.config import conf

MODIFIED_BEFORE = 'modified_before'

# Same env var names as mcweb config
MCWEB_TOKEN = conf.MCWEB_TOKEN
MCWEB_URL = conf.MCWEB_URL

logger = logging.getLogger('mcweb_api')


class MCWebError(Exception):
    """class for MCWebApi error"""


class MCWebAPI:
    def __init__(self, timeout: Optional[float] = None):
        # mcweb seems to be closing after every request,
        # but maybe (she turned me into a newt!) it will get better
        self._session = requests.sessions.Session()
        self.timeout = timeout

    def __enter__(self) -> "MCWebAPI":
        # logger.debug("__enter__")
        return self

    def __exit__(self, *args: Any) -> None:
        # logger.debug("__exit__")
        self._session.close()

    def _request(self, method: str, url: str, **kws: Any) -> Any:
        if not MCWEB_URL:
            raise MCWebError('MCWEB_URL not set')

        headers = {}
        if MCWEB_TOKEN:
            headers['Authorization'] = f"Token {MCWEB_TOKEN}"
        response = self._session.request(method, url, headers=headers,
                                         timeout=self.timeout, **kws)

        if response.status_code != 200:
            raise MCWebError(
                f"HTTP {url}: {response.status_code} {response.reason}")
        j = response.json()
        return j

    def _get(self, path: str) -> Any:
        url = f'{MCWEB_URL}/api/{path}'
        return self._request('GET', url)

    def _get_dict(self, path: str) -> Dict[str, Any]:
        r = self._get(path)
        if not isinstance(r, dict):
            raise MCWebError(f"{path} expected dict got {type(r).__name__}")
        return r

    def get_url_dict(self, url: str) -> Dict[str, Any]:
        r = self._request('GET', url)
        if not isinstance(r, dict):
            raise MCWebError(f"{url} expected dict got {type(r).__name__}")
        return r

    # top level

    def version(self) -> Dict[str, Any]:
        """
        returns dict w/ version, GIT_REV, now
        """
        return self._get_dict("version")

    # sources (directory) methods

    def feeds_url(self, since: float, before: float,
                  batch_limit: int = 1000) -> str:
        """
        return initial URL for updating feeds
        """
        return (f"{MCWEB_URL}/api/sources/feeds/"
                f"?modified_since={since}"
                f"&{MODIFIED_BEFORE}={before}"
                f"&limit={batch_limit}")


if __name__ == '__main__':
    import time

    logging.basicConfig(level=logging.DEBUG)

    with MCWebAPI() as mcweb:
        v = mcweb.version()
        print("version", v)

        url = mcweb.feeds_url(0, v['now'])
        while url:
            f = mcweb.get_url_dict(url)
            r = f['results']
            print(url, len(r))
            url = f['next']
