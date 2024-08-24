import datetime as dt
import gzip
import logging
import os.path

from sqlalchemy import text

from fetcher.config import conf
from fetcher.database.engine import engine
from fetcher.logargparse import LogArgumentParser
import fetcher.path as path
from fetcher.rss.rsswriter import RssWriter
from fetcher.stats import Stats
import fetcher.util as util

SCRIPT = 'gen_rss'              # NOTE! used for stats!!!

logger = logging.getLogger(SCRIPT)


if __name__ == '__main__':
    p = LogArgumentParser(SCRIPT, 'RSS file generator')
    # XXX include default values in help??
    p.add_argument('--days', default=conf.RSS_OUTPUT_DAYS, type=int,
                   help="number of days to (try to) output")
    p.add_argument('--output', default=path.OUTPUT_RSS_DIR,
                   help="directory for generated RSS files")
    # XXX add option to output hourly files???
    #    (if daily file exists, don't write hourly files)

    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    target_dir = args.output
    path.check_dir(target_dir)

    today = dt.date.today()
    logger.info(f"Writing daily RSS files since {today}")
    logger.info(f"  writing to {target_dir}")

    stats = Stats.get()

    def incr_files(status: str) -> None:
        stats.incr('files', labels=[('status', status)])

    def incr_stories(status: str) -> None:
        stats.incr('stories', labels=[('status', status)])

    # generate a file for each of the last N days (skipping today, which might
    # still be running)

    # join stories.feed_id to feeds.id to get feed_url for <sources/> tag,
    # it's ok if feed row doesn't exist, so left join
    query = f"""
                select s.id, s.url, s.published_at, s.domain, s.title, s.feed_id, s.sources_id, f.url as feed_url
                from stories s
                left join feeds f
                on s.feed_id = f.id
                where s.fetched_at >= :day and
                      s.fetched_at < :day_after and
                      s.url is not NULL;
                """
    qtext = text(query)

    day = today
    day_str = day.strftime("%Y-%m-%d")
    one_day = dt.timedelta(1)

    for d in range(1, args.days):
        try:
            day_after = day
            day_after_str = day_str

            day -= one_day
            day_str = day.strftime("%Y-%m-%d")

            logger.info(
                f" Working on {day_str} (day {d}) day_after {day_after_str}")
            # only do this day if it doesn't exist already
            filename = f"mc-{day_str}.rss.gz"
            compressed_filepath = os.path.join(target_dir, filename)
            if not os.path.exists(compressed_filepath):
                tmp_path = compressed_filepath + '.tmp'
                with gzip.open(tmp_path, 'wt') as outfile:
                    rsswriter = RssWriter(outfile)
                    incr_files('created')
                    rsswriter.add_header(day)
                    # grab the stories fetched on that day
                    # (ignore ones that didn't have URLs - ie. podcast feeds, which have `<enclosure url="...">` instead)
                    story_count = 0
                    with engine.begin() as connection:  # will auto-close
                        result = connection.execute(
                            qtext, {"day": day_str, "day_after": day_after_str})
                        for row in result:
                            story = row._asdict()
                            try:
                                rsswriter.add_item(story['url'], story['published_at'], story['domain'],
                                                   util.clean_str(
                                    story['title']) if 'title' in story else '',
                                    feed_url=story['feed_url'] or '',
                                    feed_id=story['feed_id'],
                                    source_id=story['sources_id'],
                                )
                                incr_stories('added')
                            except Exception as e:
                                # probably some kind of XML encoding problem,
                                # just log and skip
                                logger.warning(
                                    f"Skipped story {story['id']} - {e}")
                                incr_stories('skipped')
                            story_count += 1
                    rsswriter.add_footer()
                os.rename(tmp_path, compressed_filepath)
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
