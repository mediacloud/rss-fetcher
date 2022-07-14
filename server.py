import logging
import os
import sentry_sdk
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
# from sentry_sdk.integrations.logging import ignore_logger
from flask import send_from_directory
from itertools import chain
from functools import wraps
from typing import Dict, List, Union
from fastapi import FastAPI, Query
import time
import uvicorn

import fetcher
import fetcher.database.models as models

logger = logging.getLogger(__name__)

STATUS_OK = 'ok'
STATUS_ERROR = 'error'

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


def _error_results(message: str, start_time: float, status_code: int = 400):
    """
    Central handler for returning error messages.
    :param message:
    :param start_time:
    :param status_code:
    :return:
    """
    return {
        'status': STATUS_ERROR,
        'statusCode': status_code,
        'duration': _duration(start_time),
        'message': message,
    }


def _duration(start_time: float):
    return int(round((time.time() - start_time) * 1000)) if start_time else 0


def api_method(func):
    """
    Helper to add metadata to every api method. Use this in server.py and it will add stuff like the
    version to the response. Plug it handles errors in one place, and supresses ones we don't care to log to Sentry.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            results = func(*args, **kwargs)
            return {
                'version': fetcher.VERSION,
                'status': STATUS_OK,
                'duration': _duration(start_time),
                'results': results,
            }
        except Exception as e:
            # log other, unexpected, exceptions to Sentry
            logger.exception(e)
            return _error_results(str(e), start_time)
    return wrapper


@app.get("/api/version")
@api_method
def version():
    return {}


def _prep_for_graph(counts: List[List], names: List[str]) -> List[Dict]:
    cleaned_data = [{r['day'].strftime("%Y-%m-%d"): r['stories'] for r in series} for series in counts]
    dates = set(chain(*[series.keys() for series in cleaned_data]))
    stories_by_day_data = []
    for d in dates:  # need to make sure there is a pair of entries for each date
        for idx, series in enumerate(cleaned_data):
            stories_by_day_data.append(dict(
                date=d,
                type=names[idx],
                count=series[d] if d in series else 0
            ))
    return stories_by_day_data


@app.get("/api/stories/fetched-by-day")
@api_method
def stories_fetched_counts(days: Union[int, None] = None):
    return _prep_for_graph([models.Story.recent_published_volume(limit=days)], ["stories"])


@app.get("/api/stories/published-by-day")
@api_method
def stories_published_counts(days: Union[int, None] = None):
    return _prep_for_graph([models.Story.recent_fetched_volume(limit=days)], ["stories"])


@app.get("/api/rss/<filename>")
def rss(filename: str = Query(..., description="The full name of the daily RSS file you want to retrieve")):
    return send_from_directory(directory='static', path='rss', filename=filename)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
