import logging
from typing import TYPE_CHECKING

from flask import send_from_directory
from fastapi import Query, APIRouter
if TYPE_CHECKING:  # pragma: no cover
    from flask.wrappers import Response


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/rss",
    tags=["rss"],
)


@router.get("/<filename>")
def rss(filename: str = Query(...,
        description="The full name of the daily RSS file you want to retrieve")) -> "Response":
    return send_from_directory(
        directory='static', path='rss', filename=filename)
