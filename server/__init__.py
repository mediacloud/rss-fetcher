import logging
import os
import sentry_sdk
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
# from sentry_sdk.integrations.logging import ignore_logger
import server.feeds as feeds
import server.stories as stories
import server.rss as rss

from fastapi import FastAPI
import uvicorn

from server.util import api_method
import fetcher

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
app.include_router(stories.router)
app.include_router(rss.router)

SENTRY_DSN = os.environ.get('SENTRY_DSN', None)  # optional centralized logging to Sentry
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, release=fetcher.VERSION)
    # make sure some errors we don't care about don't make it to sentry
    # ignore_logger("requests")
    logger.info("  SENTRY_DSN: {}".format(SENTRY_DSN))
    try:
        app.add_middleware(SentryAsgiMiddleware)
    except Exception:
        # pass silently if the Sentry integration failed
        pass
else:
    logger.info("Not logging errors to Sentry")


@app.get("/api/version")
@api_method
def version():
    return {'GIT_REV': os.environ.get('GIT_REV')}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
