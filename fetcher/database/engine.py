"""
Import only as needed
"""

# PyPI:
from sqlalchemy import create_engine

# local:
from fetcher.config import conf, fix_database_url

engine = create_engine(
    fix_database_url(conf.SQLALCHEMY_DATABASE_URI),
    pool_size=conf.DB_POOL_SIZE,
    echo=conf.SQLALCHEMY_ECHO)
