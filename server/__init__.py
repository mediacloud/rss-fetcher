import logging
import os
from typing import Dict

# PyPI:
from fastapi import FastAPI
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
# from sentry_sdk.integrations.logging import ignore_logger
import uvicorn

import server.feeds as feeds
import server.rss as rss
import server.sources as sources
import server.stories as stories
from server.util import api_method
import fetcher
import fetcher.sentry

logger = logging.getLogger(__name__)

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
)
app.include_router(feeds.router)
app.include_router(rss.router)
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


@app.get("/api/version")
@api_method
def version() -> Dict:
    return {'GIT_REV': os.environ.get('GIT_REV')}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
