import datetime as dt
import inspect
import logging
import sys
import time
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Literal

if sys.version_info >= (3, 12):
    from typing import TypedDict
else:
    # for pydantic 2.12
    from typing_extensions import TypedDict

from fastapi.responses import JSONResponse
from fastapi.types import DecoratedCallable

from fetcher.stats import Stats
from fetcher.version import VERSION

if TYPE_CHECKING:
    from mypy_extensions import KwArg, VarArg

    # return type for api_method decorator
    APIMethodRet = Callable[[VarArg(Any), KwArg(Any)],
                            Coroutine[Any, Any, JSONResponse]]
else:
    APIMethodRet = Any


# upper case due to having used Enum.name
# changing would effect API users & stats labels
OKStatus = Literal['OK']
ErrorStatus = Literal['ERROR']
Status = OKStatus | ErrorStatus

STATUS_OK: OKStatus = 'OK'
STATUS_ERROR: ErrorStatus = 'ERROR'


class TimeSeriesDatum(TypedDict):
    date: dt.date
    count: int
    type: str


TimeSeriesData = list[TimeSeriesDatum]

logger = logging.getLogger(__name__)


class ApiResultBase(TypedDict):
    duration: int               # ms
    version: str


class ApiResultOK(ApiResultBase):
    status: OKStatus
    results: dict


class ApiResultERROR(ApiResultBase):
    status: ErrorStatus
    statusCode: int
    message: str


ApiResults = ApiResultOK | ApiResultERROR


def _duration(start_time: float, status: Status, name: str) -> int:
    """
    return request duration in ms for ApiResultBase "duration".
    also log and report stats based on request name & status
    """
    # due to having used enum.name; used as a stats label!
    sec = (time.time() - start_time) if start_time else 0
    stats = Stats.get()
    stats.incr(
        'api.requests', labels=[
            ('status', status), ('name', name)])
    stats.timing('duration', sec)  # could label, but more expensive
    logger.info("endpoint: %s, status: %s, duration: %.6f sec",
                name, status, sec)
    return int(round(sec * 1000))


def api_method(func: DecoratedCallable) -> APIMethodRet:
    """
    Decorator for API methods: wrap responses and add metadata (version, duration, etc)
    Plus it handles errors in one place, and supresses ones we don't care to log to Sentry.

    Returns a JSONResponse for Pydantic v2, which wants to validate responses
    based on the typing of the (unwrapped) endpoint function; the (JSON)Response
    return subverts that!

    The precommit checks run mypy, so the endpoints should be
    statically check to be returning what they claim, however the
    redoc output may not reflect the wrapper!
    """
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> JSONResponse:
        start_time = time.time()
        # could use __qualname__ if needed:
        name = f"{func.__module__}.{func.__name__}"
        status: Status
        ret: dict[str, Any]     # ApiResults
        try:
            if inspect.iscoroutinefunction(func):
                results = await func(*args, **kwargs)
            else:
                results = func(*args, **kwargs)
            status = STATUS_OK
            ret = {             # ApiResultOK
                'duration': _duration(start_time, status, name),
                'version': VERSION,
                'status': status,
                'results': results,
            }
        except Exception as e:
            # log other, unexpected, exceptions to Sentry
            logger.exception(e)

            # NOTE! str(Exception("foo")) returns "foo"
            message = str(e)

            status = STATUS_ERROR
            ret = {             # ApiResultError
                'duration': _duration(start_time, status, name),
                'version': VERSION,
                'status': status,
                'statusCode': 400,
                'message': message,
            }
        return JSONResponse(ret)

    return wrapper
