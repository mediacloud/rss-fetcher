import datetime
import logging
import datetime as dt
import os.path
from feedgen.feed import FeedGenerator

from fetcher import base_dir, VERSION
import fetcher.database.queries as queries

TARGET_DIR = os.path.join(base_dir, "fetcher", "static")

logger = logging.getLogger(__name__)

if __name__ == '__main__':

    today = dt.date.today()
    logger.info("Writing daily RSS files since {}".format(today))

    # generate a file for each of the last 30 days
    for d in range(1, 30):
        day = today - datetime.timedelta(d)
        logger.info(" Working on {} (day {})".format(day, d))
        # only do this day if it doesn't exist already
        filename = "mc-{}.rss".format(day.strftime("%Y-%m-%d"))
        filepath = os.path.join(TARGET_DIR, filename)
        if os.path.exists(filepath):
            logger.warning("  Skipping - file already exists at {}".format(filepath))
            continue
        # start a feed
        fg = FeedGenerator()
        fg.title("Media Cloud URL Snapshot for {}".format(day))
        fg.description("Auto generated feed of all stories discovered on the specified day - {}".format(VERSION))
        fg.link(href="https://mediacloud.org/")
        # metadata
        # grab the stories fetched on that day
        story_count = 0
        for story in queries.process_stories_fetched_on(day):
            fe = fg.add_entry()
            fe.id(story['guid'])
            fe.link(href=story['url'])
            fe.pubdate(story['published_at'])
            fe.content("")
            story_count += 1
        fg.rss_file(filepath)
        logger.info("   Found {} stories".format(story_count))
        logger.info("   Wrote out to {}".format(filepath))

    logger.info("Done")
