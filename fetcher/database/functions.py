"""
Postgresql functions not (yet?) supplied by SQLAlchemy
"""

from sqlalchemy.ext.compiler import compiles
import sqlalchemy.sql.functions as functions
from sqlalchemy.sql import expression
from sqlalchemy.types import Numeric

# Phil October 2022
if hasattr(functions, 'greatest'):
    greatest = functions.greatest
else:
    # https://docs.sqlalchemy.org/en/14/core/compiler.html#greatest-function
    # (NOTE: has special cases for non-PG dbs)

    class greatest(expression.FunctionElement):
        type = Numeric()
        name = 'greatest'
        inherit_cache = True

    @compiles(greatest)
    def default_greatest(element, compiler, **kw):
        return compiler.visit_function(element)
