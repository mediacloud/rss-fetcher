from typing import Any, cast

import sqlalchemy.orm as orm
from sqlalchemy.engine.cursor import CursorResult
from sqlalchemy.engine.result import Result

from fetcher.database.engine import engine

SessionType = orm.Session

# factory for SesionType with presupplied parameters:
Session = orm.sessionmaker(bind=engine)


def result_rowcount(ret: Result[Any]) -> int:
    """
    take session.execute(update/delete) result, return modified row count
    """
    return cast(CursorResult[Any], ret).rowcount
