import logging
import os
from typing import Dict

# PyPI:
from fastapi import FastAPI
from fastapi.routing import Mount
from fastapi.staticfiles import StaticFiles
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
# from sentry_sdk.integrations.logging import ignore_logger

import fetcher
from fetcher.path import OUTPUT_RSS_DIR
import fetcher.sentry

import server.feeds as feeds
import server.rss_entries as rss_entries
import server.sources as sources
import server.stories as stories
from server.util import api_method

logger = logging.getLogger(__name__)

# startup fails if OUTPUT_RSS_DIR does not yet exist!
if not os.path.isdir(OUTPUT_RSS_DIR):
    logger.info("creating %s", OUTPUT_RSS_DIR)
    os.makedirs(OUTPUT_RSS_DIR)

app = FastAPI(
    title="RSS Fetcher",
    description="Regularly fetch RSS files",
    version=fetcher.VERSION,
    license_info={
        "name": "The MIT License"
    },
    contact={
        "name": "Rahul Bhargava",
        "email": "r.bhargava@northeastern.edu",
        "url": "https://mediacloud.org"
    },
    routes=[
        # works _BUT_ logs as "GET /foo HTTP/1.1" 200
        Mount("/api/rss", StaticFiles(directory=OUTPUT_RSS_DIR)),
        Mount("/rss", StaticFiles(directory=OUTPUT_RSS_DIR))
    ]
)
app.include_router(feeds.router)
app.include_router(rss_entries.router)
app.include_router(sources.router)
app.include_router(stories.router)

if fetcher.sentry.init():
    # make sure some errors we don't care about don't make it to sentry
    # ignore_logger("requests")
    try:
        app.add_middleware(SentryAsgiMiddleware)
    except Exception:
        # pass silently if the Sentry integration failed
        pass


@app.get("/api/version")        # NOTE! NOT protected!
@api_method
def version() -> Dict:
    return {'GIT_REV': os.environ.get('GIT_REV')}


# main now in scripts/server.py
# if __name__ == "__main__":
#    uvicorn.run(app, host="0.0.0.0", port=8000)
