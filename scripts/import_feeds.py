import logging
import datetime as dt
from sqlalchemy import text
import sys
from subprocess import call
import os
import csv

from fetcher.database import engine, Session
import fetcher.database.models as models


def _run_psql_command(cmd: str):
    db_uri = os.getenv('DATABASE_URI')
    call(['psql', '-Atx', db_uri, '-c', cmd])


if __name__ == '__main__':

    # prep file
    logger = logging.getLogger(__name__)
    logger.info("Feed Importer starting!")
    if len(sys.argv) != 2:
        logger.error("  You must supply a file to import from")
        sys.exit(1)
    filename = sys.argv[1]
    if filename.endswith(".gz"):
        logger.info("Importing from {}".format(filename))
        call(['gunzip', filename])
        filename = filename.replace(".gz", "")
        logger.info("  Unzipped to {}".format(filename))

    # import data
    logger.info("Importing from {}".format(filename))
    input_file = csv.DictReader(open(filename))
    with engine.begin() as conn:  # will automatically close
        result = conn.execute(text("DELETE FROM feeds;"))
        result = conn.execute(text("DELETE FROM fetch_events;"))
        result = conn.execute(text("DELETE FROM stories;"))
    with Session() as session:
        for row in input_file:
            f = models.Feed(
                id=row['id'],
                url=row['url'],
                sources_id=row['sources_id'],
                name=row['name'],
                active=True,
                created_at=dt.datetime.now()
            )
            if f.type == 'syndicated':
                session.add(f)
        session.commit()
