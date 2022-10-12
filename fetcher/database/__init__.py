from sqlalchemy.orm import sessionmaker

from fetcher.database.engine import engine

Session = sessionmaker(bind=engine)
