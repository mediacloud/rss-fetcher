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
    from sqlalchemy.sql import case, expression
    from sqlalchemy.sql.compiler import SQLCompiler
    from sqlalchemy.types import Numeric

    # from sqlalchemy 2.0.0b ext/compiler.py:
    class _greatest(expression.FunctionElement):
        type = Numeric()
        name = 'greatest'
        inherit_cache = True

    @compiles(_greatest)
    def default_greatest(element: Any, compiler: Any, **kw: Any) -> Any:
        return compiler.visit_function(element)

    greatest = _greatest
