"""
FastAPI authentication/authorization for rss-fetcher API

from https://fastapi.tiangolo.com/advanced/security/http-basic-auth/
"""

from enum import Enum
import logging
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from fetcher.config import conf


class Access(Enum):
    READ = 'read'
    WRITE = 'write'


logger = logging.getLogger(__name__)

security = HTTPBasic()


def _byteify(param: Optional[str]) -> Optional[bytes]:
    if param:
        return param.encode('utf8')
    return None


USER_BYTES = _byteify(conf.RSS_FETCHER_USER)
PASS_BYTES = _byteify(conf.RSS_FETCHER_PASS)

if not USER_BYTES or not PASS_BYTES:
    logger.error("Need RSS_FETCHER_USER and RSS_FETCHER_PASS config")


def unauthorized() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Unauthorized',
        headers={'WWW-Authenticate': 'Basic'},
    )


def access(credentials: HTTPBasicCredentials, type: Access) -> None:
    """
    raises HTTPException if access denied
    """
    # Use compare_digest, and run twice REGARDLESS, to thawt timing attacks
    # (especially easy, since we report runtime in response).
    # NOTE! compare_digest cannot handle non-ASCII strings,
    # so always UTF-8 encode.
    if USER_BYTES and PASS_BYTES:
        user_bytes = credentials.username.encode("utf8")
        pass_bytes = credentials.password.encode("utf8")
        user_ok = secrets.compare_digest(user_bytes, USER_BYTES)
        pass_ok = secrets.compare_digest(pass_bytes, PASS_BYTES)
    else:
        user_ok = pass_ok = False

    if not user_ok or not pass_ok:
        unauthorized()
    # should raise 403 Forbidden if user not allowed to write


def read_access(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    """
    called via:
    @app.get('/api/a/protected', dependencies=[Depends(read_access)])
    raises HTTPException on error.
    """
    return access(credentials, Access.READ)


def write_access(
        credentials: HTTPBasicCredentials = Depends(security)) -> None:
    """
    called via:
    @app.put('/api/a/protected', dependencies=[Depends(write_access)])
    raises HTTPException on error.
    """
    return access(credentials, Access.WRITE)
