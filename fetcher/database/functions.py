"""
Postgresql functions not (yet?) supplied by SQLAlchemy
"""

from typing import Any

import sqlalchemy.sql.functions as functions

# Phil October 2022
if hasattr(functions, 'greatest'):
    greatest = getattr(functions, 'greatest')
else:
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.sql import expression, case
    from sqlalchemy.sql.compiler import SQLCompiler
    from sqlalchemy.types import Numeric

    # from sqlalchemy 2.0.0b ext/compiler.py:
    class _greatest(expression.FunctionElement):
        type = Numeric()
        name = 'greatest'
        inherit_cache = True

    @compiles(_greatest)
    # type: ignore[no-untyped-def]
    def default_greatest(element, compiler, **kw):
        return compiler.visit_function(element)

    greatest = _greatest
