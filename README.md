MC Backup RSS Fetcher
=====================

The code Media Cloud server wasn't performing well, so we made this quick and dirty backup project. It gets a prefilled
in list of the RSS feeds MC usually scrapes each day (~130k). Then throughout the day it tries to fetch those. Every 
night it generates a synthetic RSS feed with all those URLs. 

Files are available afterwards at `http://my.server/rss/mc-YYYY-MM-dd.rss`.

See documentation in `/doc` for more details.

Install for Development
-----------------------

For development, install via standard Python approaches: `pip install -r requirements.txt`.
You'll need to setup an instance of rabbitmq to connect to (on MacOS do `brew install rabbitmq`).
Then `cp .env.template .env` and fill in the appropriate info for each setting in that file.
Create a database called "rss-fetcher-db" in Postgres, then run `alembic upgrade head` to initialize it.

Running
-------

Various scripts run each separate component:
 * `python -m scripts.import_feeds my-feeds.csv`: Use this to import from a CSV dump of feeds (a one-time operation)
 * `run-fetch-rss-feeds.sh`: Fill up the queue with new RSS URLs to fetch (run via cron every 30 mins)
 * `run-rss-workers.sh`: Start the workers that fetch feeds and pull out story URLs (run once)
 * `run-gen-daily-story-rss.sh`: Generate the daily files of URLs found on each day (run nightly)
 * `run-aws-sync.sh`: Copy all the generated daily story RSS files to an AWS bucket (run nightly)
 
