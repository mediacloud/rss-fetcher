MC Backup RSS Fetcher
=====================

The code Media Cloud server wasn't performing well, so we made this quick and dirty backup project. It gets a prefilled
in list of the RSS feeds MC usually scrapes each day (~130k). Then throughout the day it tries to fetch those. Every 
night it generates a synthetic RSS feed with all those URLs. 

Files are available afterwards at `http://my.server/rss/mc-YYYY-MM-dd.rss`.

Install for Development
-----------------------

For development, install via standard Python approaches: `pip install -r requirements.txt`.
You'll need to setup an instance of rabbitmq to connect to (on MacOS do `brew install rabbitmq`).
Then `cp .env.template .env` and fill in the appropriate info for each setting in that file.
Create a database called "rss-fetcher-db" in Postgres, then run `alembic upgrade head` to intialize it.

Running
-------

To fill up the queue with new RSS URLs to fetch, execute `run-fetch-rss-feeds.sh`

To start the workers that fetch feeds and pull out story URLs, execute `run-rss-workers.sh`.

To generate the daily files of URLs found on each day, run `run-gen-daily-story-rss.sh`.

Deploying
---------

When you make a change, edit `fetcher.VERSION` and update the `CHANGELOG.md` file with a note about what changed.

This is built to deploy via a SAAS platform, like Heroku. We deploy via [dokku](https://dokku.com). Whatever your deploy
platform, make sure to create environment variables there for each setting in the `.env.template`.

### Create the Dokku apps

1. [install Dokku](http://dokku.viewdocs.io/dokku/getting-started/installation/)
2. install the [Dokku rabbitmq plugin](https://github.com/dokku/dokku-rabbitmq)
3. install the [Dokku postgres plugin](https://github.com/dokku/dokku-postgres)
4. setup a rabbitmq queue: `dokku rabbitmq:create rss-fetcher-q`
5. setup a postgres database: `dokku postgres:create rss-fetcher-db`
6. create an app: `dokku apps:create rss-fetcher`
7. link the app to the rabbit queue: `dokku rabbitmq:link rss-fetcher-q rss-fetcher`
8. link the app to the postgres database: `dokku postgres:link rss-fetcher-db rss-fetcher`

### Release the worker app

1. setup the configuration on the dokku app: `dokku config:set BROKER_URL=http://my.rabbitmq.url SENTRY_DSN=https://mydsn@sentry.io/123 DATABASE_URL=postgresql:///rss-fetcher`
2. add a remote: `git remote add prod dokku@prod.server.org:rss-fetcher`
4. push the code to the server: `git push prod main`
5. scale it to get a worker (dokku doesn't add one by default): `dokku ps:scale rss-fetcher worker=1`

### Setup the fetcher

1. scale it to get a regular fetcher (dokku doesn't add one by default): `dokku ps:scale rss-fetcher fetcher-rss=1` (this will run the script once)
2. scale it to get a nightly generator (dokku doesn't add one by default): `dokku ps:scale rss-fetcher gen-daily-file=1` (this will run the script once)
3. add a cron job to fetch during feeds during the day: `*/30 * * * * dokku --rm run rss-fetcher fetcher-rss /app/run-fetch-rss-feeds.sh >> /var/tmp/run-fetch-rss-feeds-cron.log 2>&1`
4. add a cron job something like this to fetch new stories every night: `15 1 * * * dokku --rm run rss-fetcher gen-daily-file /app/run-gen-daily-story-rss.sh >> /var/tmp/run-gen-dailt-story-rss-cron.log 2>&1`

### Setup Database Backups

The local logging database is useful for future interrogation, so we back it up.

1. `dokku postgres:backup-auth rss-fetcher-db AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY`
2. `dokku postgres:backup-schedule rss-fetcher-db "0 2 * * *" rss-fetcher-backup`
