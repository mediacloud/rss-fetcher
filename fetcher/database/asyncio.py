from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio.session import async_sessionmaker

from fetcher.config import conf, fix_database_url

async_engine = create_async_engine(
    fix_database_url(conf.SQLALCHEMY_DATABASE_URI),
    pool_size=conf.DB_POOL_SIZE,
    echo=conf.SQLALCHEMY_ECHO)

# https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#preventing-implicit-io-when-using-asyncsession
AsyncSession = async_sessionmaker(async_engine, expire_on_commit=False)
