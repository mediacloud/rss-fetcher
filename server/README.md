rss-fetcher API server
----------------------

web-search is currently the only client of this API, and the most
complete test can be run by running
[rss_fetcher_api.py](https://github.com/mediacloud/web-search/blob/main/mcweb/backend/sources/rss_fetcher_api.py)
after setting the `RSS_FETCHER_USER`, `RSS_FETCHER_PASS` and
`RSS_FETCHER_URL` environment variables (rss_fetcher_api.py's only
dependence is `requests`)
