import logging
import datetime as dt
from sqlalchemy import text

from fetcher import MAX_FEEDS
import fetcher.tasks as tasks
from fetcher.database import engine, Session
import fetcher.database.models as models


if __name__ == '__main__':

    logger = logging.getLogger(__name__)
    logger.info("Starting Feed Queuer")
    now = dt.datetime.now()

    # find all the feeds to update
    query = "select id, url, last_fetch_hash from feeds " \
            "where ((last_fetch_attempt is NULL) or (last_fetch_attempt <= NOW() - INTERVAL '1 DAY'))" \
            "  and type='syndicated' and active=true " \
            "order by last_fetch_attempt ASC, id DESC " \
            "LIMIT {}" \
            .format(MAX_FEEDS)
    feeds_needing_update = []
    with engine.begin() as connection:  # will automatically close
        result = connection.execute(text(query))
        for row in result:
            feeds_needing_update.append(row['id'])
            tasks.feed_worker.delay(dict(row))

    # mark that we've queued them
    with Session.begin() as session:  # this automatically commits and closes
        for feed_id in feeds_needing_update:
            f = session.query(models.Feed).get(feed_id)
            f.last_fetch_attempt = now

    logger.info("  queued {} feeds".format(len(feeds_needing_update)))
