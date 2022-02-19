from sqlalchemy.orm import sessionmaker
from fetcher import engine

Session = sessionmaker(bind=engine)
