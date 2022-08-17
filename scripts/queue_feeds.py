import logging
import datetime as dt
from sqlalchemy import text
import sys

from fetcher import MAX_FEEDS
import fetcher.tasks as tasks
from fetcher.database import engine, Session
import fetcher.database.models as models


if __name__ == '__main__':

    logger = logging.getLogger(__name__)
    logger.info("Starting Feed Queueing")
    now = dt.datetime.now()

    # support passing in a specific feed id on the command line
    arg_count = len(sys.argv)
    query_start = "select id, url, last_fetch_hash, sources_id from feeds "
    feed_id = None
    try:
        feed_id = int(sys.argv[1])
    except (ValueError, IndexError):
        pass
    if feed_id:
        query = query_start + """
            where id = {}
        """.format(feed_id)
    else:
        # no id, so default to regular automated behaviour:
        # Find some active feeds we need to check. This includes ones that:
        #  a) we haven't attempted to fetch it yet OR
        #  b) we haven't attempted to fetch it recently  OR
        #  c) we attempted to fetch it, but it hasn't succeeded ever
        # AND excludes ones that have failed to respond with content 3 times in a row
        query = query_start + """
            where (
                (last_fetch_attempt is NULL)
                OR
                (last_fetch_attempt <= NOW() - INTERVAL '1 DAY')
                OR
                ((last_fetch_attempt is not NULL) and (last_fetch_success is NULL))
              ) and (active=true) and ((last_fetch_failures is NULL) OR (last_fetch_failures < 3))
            order by last_fetch_attempt ASC, id DESC
            LIMIT {}
        """.format(MAX_FEEDS)

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
            fe = models.FetchEvent.from_info(feed_id, models.FetchEvent.EVENT_QUEUED)
            session.add(fe)

    logger.info("  queued {} feeds".format(len(feeds_needing_update)))
