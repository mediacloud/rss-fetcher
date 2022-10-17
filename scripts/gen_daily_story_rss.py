import datetime
import logging
import datetime as dt
import os.path
from sqlalchemy import text
import gzip

from fetcher.database.engine import engine
from fetcher.logargparse import LogArgumentParser
import fetcher.path as path
import fetcher.rss.rsswriter as rsswriter
from fetcher.stats import Stats
import fetcher.util as util

SCRIPT = 'gen_rss'              # NOTE! used for stats!!!

logger = logging.getLogger(SCRIPT)
stats = Stats.init(SCRIPT)


def incr_files(status):
    stats.incr('files', labels=[['status', status]])


def incr_stories(status):
    stats.incr('stories', labels=[['status', status]])


if __name__ == '__main__':
    p = LogArgumentParser(SCRIPT, 'RSS file generator')
    # XXX include default values in help??
    p.add_argument('--days', default=14, type=int,
                   help="number of days to (try to) output")
    p.add_argument('--output', default=path.OUTPUT_RSS_DIR,
                   help="directory for generated RSS files")
    # XXX add option to output hourly files???
    #    (if daily file exists, don't write hourly files)

    # info logging before this call unlikely to be seen:
    args = p.parse_args()       # parse logging args, output start message

    target_dir = args.output
    path.check_dir(target_dir)

    today = dt.date.today()
    logger.info(f"Writing daily RSS files since {today}")
    logger.info(f"  writing to {target_dir}")

    # generate a file for each of the last N days (skipping today, which might
    # still be running)
    for d in range(1, args.days):
        try:
            day = today - datetime.timedelta(d)
            day_str = day.strftime("%Y-%m-%d")
            logger.info(f" Working on {day_str} (day {d})")
            # only do this day if it doesn't exist already
            filename = f"mc-{day_str}.rss.gz"
            compressed_filepath = os.path.join(target_dir, filename)
            if not os.path.exists(compressed_filepath):
                with gzip.open(compressed_filepath, 'wt') as outfile:
                    incr_files('created')
                    rsswriter.add_header(outfile, day)
                    # grab the stories fetched on that day
                    # (ignore ones that didn't have URLs - ie. podcast feeds, which have `<enclosure url="...">` instead)
                    story_count = 0
                    query = f"""
                        select id, url, guid, published_at, domain, title
                        from stories
                        where fetched_at::date = '{day_str}'::date and url is not NULL
                    """
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
                                    f"Skipped story {story['id']} - {e}")
                                incr_stories('skipped')
                            story_count += 1
                    rsswriter.add_footer(outfile)
                logger.info(f"   Found {story_count} stories")
                logger.info(f"   Wrote out to {compressed_filepath}")
            else:
                incr_files('exists')
                logger.info(
                    "  Skipping - file already exists at {}".format(compressed_filepath))
        except Exception as exc:
            logger.exception(exc)
            logger.error(
                "Had an error on day {}, skipping due to: {}".format(
                    d, str(exc)))
            incr_files('failed')
    logger.info("Done")
