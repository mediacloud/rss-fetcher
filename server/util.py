from itertools import chain
from functools import wraps
import time
from typing import Dict, List
import logging

from fetcher import VERSION

STATUS_OK = 'ok'
STATUS_ERROR = 'error'

logger = logging.getLogger(__name__)


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
                'version': VERSION,
                'status': STATUS_OK,
                'duration': _duration(start_time),
                'results': results,
            }
        except Exception as e:
            # log other, unexpected, exceptions to Sentry
            logger.exception(e)
            return _error_results(str(e), start_time)
    return wrapper


def as_timeseries_data(counts: List[List], names: List[str]) -> List[Dict]:
    cleaned_data = [{r['day'].strftime(
        "%Y-%m-%d"): r['stories'] for r in series} for series in counts]
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
