import sqlalchemy.orm as orm

from fetcher.database.engine import engine

SessionType = orm.Session

# factory for SesionType with presupplied parameters:
Session = orm.sessionmaker(bind=engine)
