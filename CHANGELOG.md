
Change Log
==========

## v0.16.12 2025-07-17

* Add top domain stories gauge

## v0.16.12 2025-05-19

* Add sources.recent gauges

## v0.16.11 2025-04-21

* Add scripts/rss-fetcher-stats.py run-stats.sh, run from Procfile
* Add .pre-commit-{config.yaml,run.sh}
  + runs isort, autoflake, autopep8, mypy
  + removed unused imports
* Add pyproject.toml
* Add Makefile
  + "make requirements" generates requirements.txt
  + "make lint" runs pre-commits
* Removed autopep8.sh, mypy-requirements.txt
* Add fetcher.version: get VERSION from pyproject.toml

## v0.16.10 2025-03-17

* dokku scripts updates
* add update_feeds --full-update and --dry-run
* run --full--update at 04:15

## v0.16.9 2024-10-12

* update to mcmetadata v1.1.0 for:
  + insecure_requests_session()
  + is_non_news_domain()
* update to sitemap-tools v2.0.0
* mypy.sh: detect changes to mypy-requirements.txt
* update dokku-scripts/http-proxy.sh for new version of dokku on tarbell
* handle scheme-less link URLs
* ran autopep8.sh
* bring back improvements from web-search dokku-scripts
  + use private config repo
  + update airtable

## v0.16.8 2024-09-08

* fetcher/config.py: remove REDIS_URL, add UNDEAD_FEED{S,_MAX_DAYS}
* fetcher/tasks.py: if UNDEAD_FEEDS set:
	1. never disable feeds
	2. use UNDEAD_FEED_MAX_DAYS instead of MAXIMUM_BACKOFF_MINS
	   (if failures > MAX_FAILURES)

## v0.16.7 2024-09-03

* scripts/gen_daily_story_rss.py: use date range for faster query
* fetcher/rss/rsswriter.py: read item template once
* requirements.txt: update to sitemap-tools v1.1.0 w/ HTML detection
* fetcher/tasks.py: no need for HTML detection

## v0.16.6 2024-08-16

* RSS sync crontab fix

## v0.16.5 2024-08-16

* update dokku-scripts/instance.sh to disable sync of RSS files to S3
* remove mcweb network, use MCWEB_URL from .prod

## v0.16.4 2024-08-15

* update runtime.txt to python-3.10.14
* add sources_id index to stories table

## v0.16.3 2024-08-02

* add sitemap parsing

## v0.16.2 2024-04-07

* add HTTP_KEEP_CONNECTION_HEADER (defaults to off)
	stops akamai https npr.org feeds from timing out

## v0.16.1 2024-03-23

* server/rss_entries.py: add fetched_at

## v0.16.0 2024-03-19

* dokku-scripts/config.sh: require/pick-up MCWEB_TOKEN
* scripts/gen_daily_story_rss.py: generate items even if feed_url unavailable
* new server/rss_entries.py: add /api/rss_entries endpoint

## v0.15.1 2024-02-15

* use mcmetadata (v0.12.0) webpages.MEDIA_CLOUD_USER_AGENT

## v0.15.0 2023-08-07

* updated dashboards directory json files
* create OUTPUT_RSS_DIR if it doesn't yet exist!
* cleanup from runs of autopep8.sh and mypy.sh
* add <source/> tag to RSS file

## v0.14.9 2023-10-16

* fix check function in scripts/update_feeds.py: was not picking up new feeds!

## v0.14.8 2023-10-14

* redeploy with latest mcmetadata
* update to python-3.10.13
* dashboards/rss-fetcher-alerts.json updated
* dokku-scripts/http-proxy.sh: add helpful message
* dokku-scripts/install-dokku.sh: fix apt update command
* dokku-scripts/instance.sh: remove double echo

## v0.14.7 2023-05-18

* added LICENSE (Apache 2.0)
* dokku-scripts/config.sh: set RSS_OUTPUT_DAYS=90 for production, removed MAX_FEEDS
* server/sources.py: use queued.isnot(True)
* .env.template: removed MAX_FEEDS

## v0.14.6 2023-05-05

* fetcher/config.py: lower AUTO_ADJUST_MIN_POLL_MINUTES default to 10 minutes(!)
* dokku-scripts/instance.sh: fix MCWEB URL, redis removal

## v0.14.5 2023-04-24

* scripts/db_archive.py: fix for SQLAlchemy 2.0
* gen_daily_story_rss.py: fix for SQLAlchemy 2.0, write to .tmp file and rename
* dokku-scripts/configure.sh: lower prod/staging worker count to 16
* updated runtime.txt to Python 3.10.10 for security fixes

## v0.14.4 2023-04-23

* server (API) fixes for SQLAlchemy 2.0

## v0.14.3 2023-04-23

* Raise staging/prod workers to 32
* Raise default concurrency to 2
* Fudge SBItem.next_start to avoid extra waits
* Log feeds in Manager process

## v0.14.2 2023-04-23

* Update to sqlalchemy 2.0, psycopg 3.1
* Use "rank" in headhunter ready query (from legacy crawler_provider/__init__.py)
* All server methods are async

## v0.14.1 2023-04-22

* dokku-scripts cleanup
* add RSS_FETCH_READY_LIMIT
* update prod dashboard .json file

## v0.14.0 2023-04-22

NOTE! Untuned!! almost certainly queries database more than needed!

* fully adaptive fetching (adjusts poll_minutes both up and down)
* replace work queue with direct process management
  + replace scripts/{queue_feeds,worker}.py with scripts/fetcher.py
  + removed fetcher/queue.py
  + added fetcher/{direct,headhunter,scoreboard}.py
* use official PyPI mediacloud package for scripts/update_feeds.py
* dokku-scripts improvements:
  + moved dokku instance configuration to config.sh
  + run config.sh from push.sh
  + instance.sh saves INSTANCE_SH_GIT_HASH, checked by push.sh

## v0.13.0 2023-03-14

Implement auto-adjustment of Feed.poll_minutes

## v0.12.15 2023-02-20

* dokku-scripts/push.sh: up prod workers from 10 to 12
* add server/sources.py: add /api/sources/N/stories/{fetched,published}_by_day}

## v0.12.14 2023-02-17

* fetcher/stats.py: add break to loops: fix double increments!
* fetcher/tasks.py:
    + split "dup" from "skipped"
    + always call mcmetadata.urls.is_homepage_url (to detect bad urls early)
    + keep saved_count
    + report queue length as gauge at end of processing
* scripts/poll_update.py: handle new "N skipped / N dup / N added" reports
* scripts/queue_feeds.py: add "added2" counter
* removed unused dokku-scripts/sync-feeds.sh
* dokku-scripts/push.sh: complain about unknown arguments
* dokku-scripts/instance.sh: run scripts using "enter"
* Procfile: remove generator/archiver/update

## v0.12.13 2023-02-12

* Procfile: queue feeds once a minute
* fetcher/config.py
    + make MAX_FAILURES default 10 (was 4)
    + add SKIP_HOME_PAGES config (default to off)
* fetcher/tasks.py
    + re-raise JobTimeout in fetch_and_process_feed
    + honor SKIP_HOME_PAGES
* scripts/poll_update.py
    + update feeds one at a time
    + add --fetches and --max-urls for experimentation

## v0.12.12 2023-02-01

* add HTTP_CONDITIONAL_FETCH config variable
* new doc/columns.md -- explain db columns
* new dokku-scripts/dburl.sh
* scripts.poll_update: add options for experimentation

## v0.12.11 2023-01-28

Fix more parse errors

* fetcher/tasks.py: feed response.content to feedparser:
	response.text decodes utf-16 as utf-8 (w/ bad results)
* dokku-scripts/test-feeds.psql: add feeds w/ doctype html, html, utf-16
	remove www.mbc.mw urls (all HTML)
* CHANGELOG.md: add dates on 0.12.* versions

## v0.12.10 2023-01-23

Fix spurrious parse errors:

* dokku-scripts/test-feeds.psql: create feeds table with small test set
* fetcher/config.py: add SAVE_PARSE_ERRORS param
* fetcher/path.py: add PARSE_ERROR_DIR
* fetcher/tasks.py: ignore feedparser "bozo"; check "version" only
	honor SAVE_PARSE_ERRORS
* .env.template: add TZ, SAVE_PARSE_ERRORS

## v0.12.9 2023-01-20

* dokku-scripts/instance.sh: speed up deployment, fix mcweb config
* dokku-scripts/push.sh: vary workers acording to instance type
	add git:set
* fetcher/config.py: add FAST_POLL_MINUTES
* fetcher/database/models.py: comment
* scripts/poll_update.py:
  + use FAST_POLL_MINUTES
  + don't overwrite poll period if less than or equal
  + add stats
  + take pidfile lock before gathering candidates
* scripts/queue_feeds.py:
  + order by id % 1001
  + stats for stray catcher

## v0.12.8 2023-01-13

Reduce default fetch interval to 6 hours (from 12):

* fetcher/config.py: change _DEFAULT_DEFAULT_INTERVAL_MINS to 6 hours!
* dokku-scripts/randomize-feeds.sh: change from 12 to 6 hours

Implement Feed.poll_minutes override, for feeds that publish
uniformly short lists of items, with little overlap when polled normally:

* fetcher/database/models.py: add poll_minutes (poll period override)
	(currently only set by scripts/poll_update.py
* fetcher/database/versions/20230111_1237_add_poll_minutes.py: migration
* fetcher/tasks.py: implement policy changes to honor poll_minutes
* scripts/poll_update.py: script to set poll_minutes for "short fast" feeds

Administrivia:

* dokku-scripts/instance.sh:
  + fix/use app_http_url function
  + save feed update script output
  + add crontab entry for poll_updates

Create/use global /storage/lock directory:

* fetcher/path.py: add LOCK_DIR
* fetcher/pidfile: use fetcher.path.LOCK_DIR, create if needed

Cleanup:

* scripts/update_feeds.py: import LogArgumentParser in main

## v0.12.7 2023-01-03

* Procfile: add "update" for update_feeds.py
* instance.sh:
  + configure rss-fetcher AND mcweb Dokku app networking
  + install crontab entry for update in production
* Fix mypy complaint about _MAXHEADERS
* Add MAX_URL -- max URL length to accept
* Add /api/{feeds,sources}/ID/stories endpoints
* New: fetcher.pidfile -- create exclusion locks for scripts
* New: fetcher/mcweb_api.py
* scripts/update_feeds.py:
  + use fetcher.mcweb_api
  + change defaults
  + use fetcher.pidfile
  + --sleep-seconds takes float
  + add --reset-next-url
  + require created_at
* fetcher/database/property.py: add logging

## v0.12.6 2022-12-26

* Update User-Agent to old system string plus plus in front of URL
     (rssfeeds.usatoday.com returning HTML w/ browser U-A string)
* Accept up to 1000 HTTP headers in responses
     (www.lexpress.fr was sometimes sending more than 100?)

## v0.12.5 2022-12-21

* Add /api/sources/N/fetch-soon (randomizes next_fetch_attempt)
* Add Feed.rss_title column, always update Feed.name from mcweb
* Add MAXIMUM_INTERVAL_MINS from meatspace review
* Add properties.py: section/key/value store
* scripts/update_feeds.py:
  + update to use mcweb API
  + improve logging
  + use properties
  + add --reset-last-modified
* autopep8.sh: ignore venv*
* runtime.txt: update to 3.9.15 due to vulnerability

## v0.12.4 2022-12-10

* /api/stories/by-source endpoint
* Honor SQLALCHEMY_ECHO for debug
* Fix exception in parse exception handler!
* dokku-scripts/push.sh:
  + fix push.log
  + check for push errors
  + add --force-push
* start of feed syncing scripts (not ready)

## v0.12.3 2022-12-10?

* scripts/queue_feeds.py: fix queuing feeds by number
* fetcher/tasks.py:
   + ignore feedparser charset (etc) errors
   + detect "temporary" DNS errors, treat as softer than SOFT!
   + use HTTP Retry-After values
   + only randomize 429 errors, after range checks & backoff scaling
   + don't round failure count multiplier
   + log prev_system_status when clearing last_fetch_failures
	(to see/understand what errors are transient)
   + Add Feed.last_new_stories column
   + Set system_status to Working when same hash or no change
* fetcher/rss/item.template: output one RSS item per line
* dashboards -- NEW: json files for Grafana dashboards
* scripts/import_feeds.py: add --delete-{fetch-events,stories}
* dokku-scripts/instance.sh: add per-user .pw file
* server/auth.py -- NEW HTTP Basic authentication
* server/{feeds,sources,stories}.py: add authentication
* server/feeds.py: add /api/feeds/ID/fetch-soon

## v0.12.2 2022-11-19

* fetcher/config.py: fix comments
* doc/deployment.md: update
* add/use conf.LOG_BACKUP_COUNT
* fetcher/tasks.py: add "clearing failure count" log message
* treat HTTP 504 (gateway timeout) as a soft error
* scripts/db_archive.py: fix log message
* dokku-scripts/instance.sh: remove obsolete RSS_FILE_PATH variable

## v0.12.1 2022-11-09

* fetcher/config.py: drop TASK_TIMEOUT_SECONDS back to 180
* fetcher/logargparse.py: fix --logger-level/-L
* fetcher/tasks.py: clean up exception handling (pull up to fetch_feed)
	use fresh session for update_feeds;
	sentry.io issue BACKUP-RSS-FETCHER-67M
* fetcher/tasks.py: fetches_per_minute returns float
* fetcher/tasks.py: handle 'always' in _feed_update_period_mins & catch KeyErrors,
	log exceptions, log unknown period names
* dokku-scripts/push.sh: fix VERSION extraction; make more verbose
	require staging & prod to be pushed only to mediacloud
* scripts/db_archive.py: compress stories on the fly, fix headers, add .csv
* scripts/queue_feeds.py: refactor to allow more command line params and
	fix command line feeds; move FetchEvent creation & feed update to queue_feeds.
	multiply fetches_per_minute before rounding (used to truncate then multiply).
* scripts/db_archive.py: use max(RSS_OUTPUT_DAYS, NORMALIZED_TITLE_DAYS)
	for story_days default.  Display default values in help message.
* NEW: dokku-scripts/randomize-feeds.sh: randomize feed.next_fetch_attempt times
* NEW: dokku-scripts/clone-db.sh: clone production database & randomize
* doc/deployment.md: update
* scripts/queue_feeds.py: if qlen==0 but db_queue!=0, clear queued feeds (fix leakage).
* fetcher/tasks.py: clear queued on insane feeds (stop leakage).

## v0.12.0 2022-11-07

Major raking by Phil Budne

* runtime.txt updated to python-3.9.13 (security fixes)

* autopep.sh runs autopep8 -a -i on all files (except fetcher/database/versions/*.py)

* mypy.sh installs and runs mypy in a virtual env. *RUNS CLEANLY!*

* All scripts take uniform command line arguments for logging, initialization, help and version (in "fetcher.logargparse"):
   ```
   -h, --help            show this help message and exit
   --verbose, -v         set default logging level to 'DEBUG'
   --quiet, -q           set default logging level to 'WARNING'
   --list-loggers        list all logger names and exit
   --log-config LOG_CONFIG_FILE
			 configure logging with .json, .yml, or .ini file
   --log-file LOG_FILE   log file name (default: main.pid.310509.log)
   --log-level {critical,fatal,error,warn,warning,info,debug,notset}, -l {critical,fatal,error,warn,warning,info,debug,notset}
			 set default logging level to LEVEL
   --no-log-file         don't log to a file
   --logger-level LOGGER:LEVEL, -L LOGGER:LEVEL
			 set LOGGER (see --list-loggers) verbosity to LEVEL (see --level)
   --set VAR=VALUE, -S VAR=VALUE
			 set config/environment variable
   --version, -V         show program's version number and exit
   ```

* fetcher.queue abstraction

   All queue access abstracted to fetcher.queue; using "rq" for work
   queue (only redis needed, allows length monitoring), saving of
   "result" (ie; celery backend) data is disabled, since we only queue
   jobs "blind" and never check for function results returned (although
   queue_feeds in --loop mode _could_ poll for results).

* All database datetimes stored _without_ timezones.

* "fetcher" module (fetcher/__init__.py) stripped to bare minimum

      (version string and fetching a few environment variables)

* All config variables in fetcher.config "conf" object

	provides mechanisms for specifying optional, boolean, integer params.

* Script startup logging

	All script startup logging includes script name and Dokku deployed git hash, followed by ONLY logging the configuration that is referenced.

* All scripts log to BASE/storage/logs/APP.DYNO.log

	Files are turned over at midnight (to filename.log.YYYY-MM-DD), seven files are kept.

* All file path information in "fetcher.path"

* Common Sentry integration in "fetcher.sentry"

        enable passing environment="staging", enabled fastapi support, rq integration

* SQLAlchemy "Session" factory moved to "fetcher.database"

        so db params only logged if db access used/needed

* All Proctab entries invoke existing ./run-....sh scripts

        Only one place to change how a script is invoked.

* "fetcher" process (scripts/queue_feeds.py) runs persistently
    (no longer invoked by crontab)
    [enabled by --loop PERIOD in Proctab]
    and: reports statistics (queue length, database counts, etc)

    + queues ready feeds every PERIOD minutes.

	    queues only the number of feeds necessary
	    to cover a day's fetch attempts divided into equal
	    sized batches (based on active enabled feeds advertised update rate, and config)

    + Allows any number of feed id's on command line.

    + Operates as before (queues MAX_FEEDS feeds) if invoked without feed ids or --loop.

    + Clears queue and exits given `--clear`

* Queue "worker" process started by scripts/worker.py
  takes common logging arguments, stats connection init
  runs a single queue worker (need to use dokku ps:scale worker=8).

     workers set process title when active, visible by ps, top:

     ```
     pbudne@ifill:~$ ps ax | grep pbudne-rss-fetcher
     4121658 ?        Rl    48:13 pbudne-rss-fetcher worker.1 feed 2023073
     4124300 ?        Rl    48:25 pbudne-rss-fetcher worker.2 feed 122482
     4127145 ?        Sl    47:34 pbudne-rss-fetcher worker.3 feed 1461182
     4129593 ?        Sl    49:49 pbudne-rss-fetcher worker.4 feed 459899
     ```

* import_feeds script gives each feed a random "next_fetch_attempt" time
    to (initially) spread workload throughout the minimum requeue time
    interval.

    *Reorganized /app/storage for non-volatile storage of logs etc;
    ```
	/app/storage/db-archive
		    /logs
		    /rss-output-files
		    /saved-input-files
    ```

* Log files are persistent across container instances, available
    (eg; for tail) on host without docker shenanigans in
    /var/lib/dokku/data/storage/....

* API server:
    * New endpoints implemented:
	+ /api/feeds/N
	    returns None or dict
	+ /api/sources/N/feeds
	    returns list of dicts
    * Enhanced endpoints:
	+ /api/version
	    return data now includes "git_rev"
	+ /api/feeds/N/history
	    takes optional `limit=N` query parameter
    * Non-API endpoint for RSS files:
	+ /rss/FILENAME


* New feeds table columns

	column                | use
	----------------------|----------------------------
	`http_etag`           | Saved data from HTTP response `ETag:` header
	`http_last_modified`  | Saved data from HTTP response `Last-Modified:` header
	`next_fetch_attempt`  | Next time to attempt to fetch the feed
	`queued`              | TRUE if the feed is currently in the work queue
	`system_enabled`      | Set to FALSE by fetcher after excess failures
	`update_minutes`      | Update period advertised by feed
	`http_304`            | HTTP 304 (Not Modified) response seen from server
	`system_status`       | Human readable result of last fetch attempt

	Also: <tt>last_fetch_failures</tt> is now a float, incremented by 0.5
	for "soft" errors that might resolve given some (more) time.

* Archiver process

	Run from crontab: archives fetch_event and stories rows based on configuration settings.

* Reports statistics via `dokku-graphite` plugin, displayed by grafana.

## v0.11.12 2022-08-22

Handle some more feed and url parsing errors. Update feed title after fetch. Switch database to merged feeds.

## v0.11.11 2022-08-12

Integrate non-news-domain skiplist from mcmetadata library.

## v0.11.10 2022-08-04

Increase default fetch frequency to twice a day.

## v0.11.9 2022-08-02

Pull in more aggresive URL query param removal for URL normalization.

## v0.11.8 2022-08-02

Disable extra verbose debugging. Also update some requirements.

## v0.11.7 2022-08-02

Fix requirements bug by forcing a minimum version of mediacloud-metadata library.

## v0.11.6 2022-07-31

Skip homepage-like URLs.

## v0.11.5 2022-07-27

Safer normalized title/url queries.

## v0.11.4 2022-07-27

Refactored database code to support testing. Also handling failure counting more robustly now.

## v0.11.3 2022-07-27

Properly save and double-check against normalized URLs for uniqueness.

## v0.11.2 2022-07-27

Better testing of RSS generation.

## v0.11.1 2022-07-27

Better handling of missing dates in output RSS files.

## v0.11.0 2022-07-27

Write out own feed so we can customize error handling and fields outputted more closely. Also fix a small URL validity
check bug fix.

## v0.10.5 2022-07-25

Fix bug in function call

## v0.10.4 2022-07-25

Requirements bump.

## v0.10.3 2022-07-19

Don't allow NULL chars in story titles.

## v0.10.2 2022-07-19

Make Celery Backend a configuration option. We default to RabbitMQ for Broker and Redis for Backend because
that is a super common setup that seems to scale well.

## v0.10.1 2022-07-18

Small bug fixes.

## v0.10.0 2022-07-15

Add feed history to help debugging, view new FetchEvents objects.

## v0.9.4 2022-07-15

Fix some date parsing bugs by using built-in approach from feed parsing library. Also add some more unit tests.

## v0.9.3 2022-07-14

Added back in a necessary index for fast querying.

## v0.9.2 2022-07-14

More debug logging.

## v0.9.1 2022-07-14

Pretending to be a browser in order to see if it fixes a 403 bug.

## v0.9.0 2022-07-14

Add `fetch_events` table for history and debugging. Also move title uniqueness check to software (not DB) to allow for
empty title fields.

## v0.8.1 2022-07-14

Rewrite main rss fetching task to make logic more obvious, and also try and streamline database handle usage.

## v0.8.0 2022-07-14

Switch to FastApi for returning counts to help debug. See `/redoc`, or `/docs` for full API documentation and Open API 
specification file.

## v0.7.5 2022-07-11

New option to log RSS info to files on disk, controlled via `SAVE_RSS_FILES` env-var (1 or 0)

## v0.7.4 2022-07-07

Small tweak to skip relative URLs. Also more debug logging.

## v0.7.3 2022-07-06

Fix bug that was checking for duplicate titles across all sources within last 7 days, instead of just within one
media source.

## v0.7.2 2022-07-06

Update requirements and fix bug related to overly aggressive marking failures.

## v0.7.1 2022-06-02

Add in more feeds from production server.

## v0.7.0 2022-05-26

Check a normalized story URL and title for uniqueness before saving, like we do on our production system. This is a 
critical de-duplication step.

## v0.6.1 2022-05-20

Generate files for yesterday (not 2 days ago) because that will make delivered results more timely. 

## v0.6.0 2022-05-16

Add in new feed. Prep to show some data on website. 

## v0.5.5 2022-04-28

More work on concurrency for prod server and related configurations. 

## v0.5.4 2022-04-27

Tweaks to RSS file generation to make it more robust.

## v0.5.3 2022-04-27

Query bug fix.

## v0.5.2 2022-04-27

Handle podcast feeds, which don't have links by ignoring them in reporting script (they have enclosures instead)

## v0.5.1 2022-04-27

Deployment work for generating daily rss files.

## v0.5.0 2022-04-27

Retry feeds that we tried by didn't respond (up to 3 times in a row before giving up).

## v0.4.0 2022-04-27

Update dependencies to latest

## v0.3.2 2022-03-25

RSS path loaded from env-var

## v0.3.1 2022-03-11

Ignore a whole bunch of errors that are expected ones

## v0.3.0 2022-03-11

Add title and canonical domain to daily feeds 

## v0.2.1 2022-02-19

Move max feeds to fetch at a time limit to an env var for easier config (`MAX_FEEDS` defaults to 1000)

## v0.2.0 2022-02-19

Restructured queries to try and solve DB connection leak bug. 

## v0.1.2 2022-02-18

Production performance-related tweaks.

## v0.1.1 2022-02-18

Make sure duplicate story urls don't get inserted (no matter where they are from). This is the quick solution to making
sure an RSS feed with stories we have already saved doesn't create duplicates.

## v0.1.0 2022-02-18

First release, seems to work.
