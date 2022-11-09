MC Backup RSS Fetcher
=====================

The code Media Cloud server wasn't performing well, so we made this quick and dirty backup project. It gets a prefilled
in list of the RSS feeds MC usually scrapes each day (~130k). Then throughout the day it tries to fetch those. Every 
night it generates a synthetic RSS feed with all those URLs. 

Files are available afterwards at `http://my.server/rss/mc-YYYY-MM-dd.rss.gz`.

See documentation in [doc/](doc/) for more details.

Install for Development
-----------------------

For development using dokku, see [doc/deployment.md](doc/development.md)

For development directly on your local machine:
1. Install postgresql & redis
2. Create a virtual environment: `python -mvenv venv`
3. Active the venv: `source venv/bin/activate`
4. Install prerequisite packages: `pip install -r requirements.txt`
5. Create a postgres user: `sudo -u postgres createuser -s MYUSERNAME`
6. Create a database called "rss-fetcher" in Postgres: `createdb rss-fetcher`
7. Run `alembic upgrade head` to initialize database.
8. `cp .env.template .env` (little or no editing should be needed)

Shell script autopep8.sh will run autopep8 on all .py files, and mypy.sh
will run type checking.  BOTH should be run before merging to main
(or submitting a pull request).

Running
-------

Various scripts run each separate component:
 * `python -m scripts.import_feeds my-feeds.csv`: Use this to import from a CSV dump of feeds (a one-time operation)
 * `run-fetch-rss-feeds.sh --loop 5`: Runs continuously, adding ready feeds to work queue.
 * `run-rss-workers.sh`: Start a single worker process servicing the work queue.
 * `run-gen-daily-story-rss.sh`: Generate the daily files of URLs found on each day (run nightly)
 * `python -m scripts.db_archive`: archive and trim fetch_events and stories tables (run nightly)

Development Docs
----------------

 * [doc/database-changes.md](doc/database-changes.md) describes how to implement database migrations.
 * [doc/stats.md](doc/stats.md) describes how monitoring is implemented.

Deployment
----------

See [doc/deployment.md](doc/deployment.md) and
[dokku-scripts/README.md](dokku-scripts/README.md)
for procedures and scripts.
