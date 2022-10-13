import datetime
import logging
import datetime as dt
import os.path
from sqlalchemy import text
import gzip
import shutil

from fetcher.config import conf
from fetcher.database.engine import engine
from fetcher import base_dir
from fetcher.logargparse import LogArgumentParser
import fetcher.rss.rsswriter as rsswriter
from fetcher.stats import Stats
import fetcher.util as util

HISTORY = 14  # number of days to ensure output: have a --days option??
SCRIPT = 'gen_rss'              # NOTE! used for stats!!!

# handle relative paths smartly for local devs
if conf.RSS_FILE_PATH[0] == "/":
    target_dir = conf.RSS_FILE_PATH
else:
    target_dir = os.path.join(base_dir, conf.RSS_FILE_PATH)

logger = logging.getLogger(__name__)
stats = Stats.init(SCRIPT)


def incr_files(status):
    stats.incr('files', labels=[['status', status]])


def incr_stories(status):
    stats.incr('stories', labels=[['status', status]])


if __name__ == '__main__':
    p = LogArgumentParser(SCRIPT, 'RSS file generator')
    # info logging before this call unlikely to be seen:
    args = p.parse_args()       # parse logging args, output start message

    today = dt.date.today()
    logger.info("Writing daily RSS files since {}".format(today))
    logger.info("  writing to {}".format(target_dir))

    # generate a file for each of the last N days (skipping today, which might
    # still be running)
    for d in range(1, HISTORY):
        try:
            day = today - datetime.timedelta(d)
            logger.info(" Working on {} (day {})".format(day, d))
            # only do this day if it doesn't exist already
            filename = "mc-{}.rss".format(day.strftime("%Y-%m-%d"))
            filepath = os.path.join(target_dir, filename)
            compressed_filepath = '{}.gz'.format(filepath)
            if not os.path.exists(compressed_filepath):
                with open(filepath, 'w') as outfile:
                    incr_files('created')
                    rsswriter.add_header(outfile, day)
                    # grab the stories fetched on that day
                    # (ignore ones that didn't have URLs - ie. podcast feeds, which have `<enclosure url="...">` instead)
                    story_count = 0
                    query = """
                        select id, url, guid, published_at, domain, title
                        from stories
                        where fetched_at::date = '{}'::date and url is not NULL
                    """.format(day.strftime("%Y-%m-%d"))
                    with engine.begin() as connection:  # will auto-close
                        result = connection.execute(text(query))
                        for row in result:
                            story = dict(row)
                            try:
                                rsswriter.add_item(outfile, story['url'], story['published_at'], story['domain'],
                                                   util.clean_str(story['title']) if 'title' in story else '')
                                incr_stories('added')
                            except Exception as e:
                                # probably some kind of XML encoding problem,
                                # just log and skip
                                logger.warning(
                                    "Skipped story {} - {}".format(story['id'], str(e)))
                                incr_stories('skipped')
                            story_count += 1
                    rsswriter.add_footer(outfile)
                logger.info("   Found {} stories".format(story_count))
                logger.info("   Wrote out to {}".format(filepath))
                # compress for storage and transmission speed
                # https://stackoverflow.com/questions/38018071/how-to-compress-a-large-file-in-python
                if not os.path.exists(compressed_filepath):
                    with open(filepath, 'rb') as f_in:
                        with open(compressed_filepath, 'wb') as f_out1:
                            with gzip.GzipFile(filepath, 'wb', fileobj=f_out1) as f_out2:
                                shutil.copyfileobj(f_in, f_out2)
            else:
                incr_files('exists')
                logger.info(
                    "  Skipping - file already exists at {}".format(compressed_filepath))
            # and delete the uncompressed to save space
            try:
                os.remove(filepath)
            except FileNotFoundError:
                pass
        except Exception as exc:
            logger.exception(exc)
            logger.error(
                "Had an error on day {}, skipping due to: {}".format(
                    d, str(exc)))
            incr_files('failed')
    logger.info("Done")
