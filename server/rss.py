"""
Access to RSS output files

NOT an API endpoint (returns XML, not JSON)
"""

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, FastAPI, Query
from fastapi.staticfiles import StaticFiles
from flask import send_from_directory
if TYPE_CHECKING:  # pragma: no cover
    from flask.wrappers import Response

from fetcher.path import OUTPUT_RSS_DIR

logger = logging.getLogger(__name__)

def mount(app: FastAPI) -> None:
    # works _BUT_ logs as "GET /foo HTTP/1.1" 200
    # _TRIED_ to put this under a router, but failed
    # see https://github.com/tiangolo/fastapi/issues/1469 ??

    # Starlette code for app.mount() says:
    #     "We no longer document this API, and its usage is discouraged."

    # Tried:
    #     from fastapi.routing import Mount
    #     app = FastAPI(......,
    #        routes=[Mount("/rss", StaticFiles(directory=OUTPUT_RSS_DIR), "rss")])
    # but logging no different.

    # This is probably because StaticFiles purpose is to make
    # static files (in various locations) look like they're in the "server root"
    app.mount("/rss", StaticFiles(directory=OUTPUT_RSS_DIR), "rss")


router = APIRouter(
    prefix="/api/rss",
    tags=["rss"],
)


@router.get("/<filename>")
def rss(filename: str = Query(...,
        description="The full name of the daily RSS file you want to retrieve")) -> "Response":
    return send_from_directory(
        directory='static', path='rss', filename=filename)
