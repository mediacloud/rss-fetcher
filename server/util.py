import datetime as dt
from enum import Enum
from functools import wraps
import inspect
from itertools import chain
import logging
import time
from typing import Any, Callable, Dict, List, Optional, TypedDict, Union

from fetcher import VERSION
from fetcher.stats import Stats


class Status(Enum):
    OK = 'ok'
    ERROR = 'error'


class TimeSeriesDatum(TypedDict):
    date: dt.date
    count: int
    type: str


TimeSeriesData = List[TimeSeriesDatum]

logger = logging.getLogger(__name__)


class ApiResultBase(TypedDict):
    status: str
    duration: int               # ms
    version: str


class ApiResultOK(ApiResultBase):  # when status == Status.OK.name
    results: Dict


class ApiResultERROR(ApiResultBase):  # when status == Status.ERROR.name
    statusCode: int
    message: str


ApiResults = Union[ApiResultOK, ApiResultERROR]


def _error_results(message: str, start_time: float, name: str,
                   status_code: int = 400) -> ApiResultERROR:
    """
    Central handler for returning error messages.
    :param message:
    :param start_time:
    :param status_code:
    :return:
    """
    status = Status.ERROR
    return {
        'status': status.name,
        'statusCode': status_code,
        'duration': _duration(start_time, status, name),
        'message': message,
        'version': VERSION,
    }


def _duration(start_time: float, status: Status, name: str) -> int:
    """
    return request duration in ms.
    also report stats based on request name & status
    """
    sec = (time.time() - start_time) if start_time else 0
    stats = Stats.get()
    stats.incr(
        'api.requests', labels=[
            ('status', status.name), ('name', name)])
    stats.timing('duration', sec)  # could label, but more expensive
    logger.info(
        f"endpoint: {name}, status: {status.name}, duration: {sec} sec")
    return int(round(sec * 1000))


# Phil: only working type signature I've found requires mypy to be installed for normal execution:
# from fastapi.types import DecoratedCallable
# from mypy_extensions import VarArg, KwArg
# def api_method(func: DecoratedCallable) -> Callable[[VarArg(Any),
# KwArg(Any)], ApiResults]:
def api_method(func: Any) -> Any:
    """
    Helper to wrap API method responses and add metadata.
    Use this in server.py and it will add stuff like the
    version to the response.

    Plus it handles errors in one place, and supresses ones we don't care to log to Sentry.
    """
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> ApiResults:
        start_time = time.time()
        # could use __qualname__ if needed:
        name = f"{func.__module__}.{func.__name__}"
        try:
            if inspect.iscoroutinefunction(func):
                results = await func(*args, **kwargs)
            else:
                results = func(*args, **kwargs)
            status = Status.OK
            return {            # update ApiResultOK if adding items!
                'version': VERSION,
                'status': status.name,
                'duration': _duration(start_time, status, name),
                'results': results,
            }
        except Exception as e:
            # log other, unexpected, exceptions to Sentry
            logger.exception(e)
            return _error_results(str(e), start_time, name)
    return wrapper
