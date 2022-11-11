Change Log
==========

## v0.12.1

	* fetcher/logargparse.py: fix --logger-level/-L
	* fetcher/tasks.py: clean up exception handling
	   sentry.io issue BACKUP-RSS-FETCHER-67M
	* push.sh: VERSION extraction; make more verbose; try to handle origin==mediacloud
	* scripts/db_archive.py: compress stories on the fly, fix headers, add .csv
	* fetcher/tasks.py: handle 'always' in _feed_update_period_mins, catch KeyErrors,
	   log exceptions, log unknown period names

## v0.12.0

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

## v0.11.12

Handle some more feed and url parsing errors. Update feed title after fetch. Switch database to merged feeds.

## v0.11.11

Integrate non-news-domain skiplist from mcmetadata library.

## v0.11.10

Increase default fetch frequency to twice a day.

## v0.11.9

Pull in more aggresive URL query param removal for URL normalization.

## v0.11.8

Disable extra verbose debugging. Also update some requirements.
`
## v0.11.7

Fix requirements bug by forcing a minimum version of mediacloud-metadata library.

## v0.11.6

Skip homepage-like URLs.

## v0.11.5

Safer normalized title/url queries.

## v0.11.4

Refactored database code to support testing. Also handling failure counting more robustly now.

## v0.11.3

Properly save and double-check against normalized URLs for uniqueness.

## v0.11.2

Better testing of RSS generation.

## v0.11.1

Better handling of missing dates in output RSS files.

## v0.11.0

Write out own feed so we can customize error handling and fields outputted more closely. Also fix a small URL validity
check bug fix.

## v0.10.5

Fix bug in function call

## v0.10.4

Requirements bump.

## v0.10.3

Don't allow NULL chars in story titles.

## v0.10.2

Make Celery Backend a configuration option. We default to RabbitMQ for Broker and Redis for Backend because
that is a super common setup that seems to scale well.

## v0.10.1

Small bug fixes.

## v0.10.0

Add feed history to help debugging, view new FetchEvents objects.

## v0.9.4

Fix some date parsing bugs by using built-in approach from feed parsing library. Also add some more unit tests.

## v0.9.3

Added back in a necessary index for fast querying.

## v0.9.2

More debug logging.

## v0.9.1

Pretending to be a browser in order to see if it fixes a 403 bug.

## v0.9.0

Add `fetch_events` table for history and debugging. Also move title uniqueness check to software (not DB) to allow for
empty title fields.

## v0.8.1

Rewrite main rss fetching task to make logic more obvious, and also try and streamline database handle usage.

## v0.8.0

Switch to FastApi for returning counts to help debug. See `/redoc`, or `/docs` for full API documentation and Open API 
specification file.

## v0.7.5

New option to log RSS info to files on disk, controlled via `SAVE_RSS_FILES` env-var (1 or 0)

## v0.7.4

Small tweak to skip relative URLs. Also more debug logging.

## v0.7.3

Fix bug that was checking for duplicate titles across all sources within last 7 days, instead of just within one
media source.

## v0.7.2

Update requirements and fix bug related to overly aggressive marking failures.

## v0.7.1

Add in more feeds from production server.

## v0.7.0

Check a normalized story URL and title for uniqueness before saving, like we do on our production system. This is a 
critical de-duplication step.

## v0.6.1

Generate files for yesterday (not 2 days ago) because that will make delivered results more timely. 

## v0.6.0

Add in new feed. Prep to show some data on website. 

## v0.5.5

More work on concurrency for prod server and related configurations. 

## v0.5.4

Tweaks to RSS file generation to make it more robust.

## v0.5.3

Query bug fix.

## v0.5.2

Handle podcast feeds, which don't have links by ignoring them in reporting script (they have enclosures instead)

## v0.5.1

Deployment work for generating daily rss files.

## v0.5.0

Retry feeds that we tried by didn't respond (up to 3 times in a row before giving up).

## v0.4.0

Update dependencies to latest

## v0.3.2

RSS path loaded from env-var

## v0.3.1

Ignore a whole bunch of errors that are expected ones

## v0.3.0

Add title and canonical domain to daily feeds 

## v0.2.1

Move max feeds to fetch at a time limit to an env var for easier config (`MAX_FEEDS` defaults to 1000)

## v0.2.0

Restructured queries to try and solve DB connection leak bug. 

## v0.1.2

Production performance-related tweaks.

## v0.1.1

Make sure duplicate story urls don't get inserted (no matter where they are from). This is the quick solution to making
sure an RSS feed with stories we have already saved doesn't create duplicates.

## v0.1.0

First release, seems to work.
