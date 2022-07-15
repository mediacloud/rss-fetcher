import logging
from flask import send_from_directory
from fastapi import Query, APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/rss",
    tags=["rss"],
)


@router.get("/<filename>")
def rss(filename: str = Query(..., description="The full name of the daily RSS file you want to retrieve")):
    return send_from_directory(directory='static', path='rss', filename=filename)

