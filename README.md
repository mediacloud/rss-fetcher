MC RSS Fetcher
==============

This is the Media Cloud "RSS Fetcher", it keeps a database of
approximately 180K RSS and Google news sitemap feeds to fetch,
shadowed from the web-search Sources database.

Then throughout the day it tries to fetch those. Every 
night it generates a synthetic RSS feed with all those URLs. 

Files are available afterwards at `http://my.server/rss/mc-YYYY-MM-dd.rss.gz`.

See documentation in [doc/](doc/) for more details.

Install for Test/Development under Dokku
----------------------------------------

See [doc/deployment.md](doc/deployment.md)

Install for Stand-Alone Development
-----------------------------------

For development directly on your local machine:
1. Install postgresql & redis
2. Create and popilate a virtual environment: `make install`
3. Active the venv: `source venv/bin/activate`
4. Create a postgres user: `sudo -u postgres createuser -s MYUSERNAME`
5. Create a database called "rss-fetcher" in Postgres: `createdb rss-fetcher`
6. Run `alembic upgrade head` to initialize database.
7. `cp .env.template .env` (little or no editing should be needed)

* mypy.sh will install mypy (and necessary types library & autopep8) and run type checking.
* autopep.sh will normalize code format

*BOTH should be run before merging to main (or submitting a pull request).*

All config parameters should be fetched via fetcher/config.py and added to .env.template

Running
-------

Various scripts run each separate component:
 * `python -m scripts.import_feeds my-feeds.csv`: Use this to import from a CSV dump of feeds (a one-time operation)
 * `run-fetch-rss-feeds.sh`: Start fetcher (leader and worker processes) (run from Procfile)
 * `run-server.sh`: Run API server (from Procfile)
 * `run-gen-daily-story-rss.sh`: Generate the daily files of URLs found on each day as needed (run hourly)
 * `python -m scripts.update_feeds` Incrementally Sync feeds from web-search server (run every five minutes most of the day)
 * `python -m scripts.update_feeds --full-sync` Sync all feeds from web-search server (run nightly)
 * `python -m scripts.db_archive`: archive and trim fetch_events and stories tables (run nightly)
 * `run-stats.sh` report feed and source stats to statsd/graphite/grafana for vitals page (run from Procfile).

All crontab entries set up by `dokku-scripts/crontab.sh` (must be run as root)

NOTE! Cloud backup of production database must be done manually: see doc/deployment.md.

Pruning of cloud backups done by system-dev-ops/postgres/prune-backups (must be installed separately).

Development Docs
----------------

 * [doc/database-changes.md](doc/database-changes.md) describes how to implement database migrations.
 * [doc/stats.md](doc/stats.md) describes how monitoring is implemented.

Deployment
----------

See [doc/deployment.md](doc/deployment.md) and
[dokku-scripts/README.md](dokku-scripts/README.md)
for procedures and scripts.
