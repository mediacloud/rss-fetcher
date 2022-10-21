"""
Postgresql functions not (yet?) supplied by SQLAlchemy
"""

from typing import Any

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.compiler import TypeCompiler
import sqlalchemy.sql.functions as functions
from sqlalchemy.sql import expression
from sqlalchemy.types import Numeric

# Phil October 2022
if hasattr(functions, 'greatest'):
    greatest = functions.greatest  # type: ignore[attr-defined]
else:
    # https://docs.sqlalchemy.org/en/14/core/compiler.html#greatest-function
    # (NOTE: has special cases for non-PG dbs)

    class _greatest(expression.FunctionElement):
        type = Numeric()
        name = 'greatest'
        inherit_cache = True

    @compiles(_greatest)
    def default_greatest(element: _greatest,
                         compiler: TypeCompiler,
                         **kw: Any) -> str:
        return compiler.visit_function(element)

    greatest = _greatest
