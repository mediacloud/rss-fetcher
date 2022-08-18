Deploying
=========

This is built to deploy via a PaaS host, like Heroku. We deploy via [dokku](https://dokku.com). Whatever your deploy
platform, make sure to create environment variables there for each setting in the `.env.template`.

Setup (Dokku)
-------------

### Create the Dokku apps

1. [install Dokku](http://dokku.viewdocs.io/dokku/getting-started/installation/)
2. install the [Dokku rabbitmq plugin](https://github.com/dokku/dokku-rabbitmq)
3. install the [Dokku redis plugin](https://github.com/dokku/dokku-redis)
4. install the [Dokku postgres plugin](https://github.com/dokku/dokku-postgres)
5. setup a rabbitmq queue: `dokku rabbitmq:create rss-fetcher-broker-q`
6. setup a redis queue: `dokku redis:create rss-fetcher-backend-q`
7. setup a postgres database: `dokku postgres:create rss-fetcher-db`
12. create an external storage dir for generated RSS files: `dokku storage:ensure-directory rss-fetcher-daily-files`
8. create an app: `dokku apps:create rss-fetcher`
9. link the app to the rabbit queue: `dokku rabbitmq:link rss-fetcher-broker-q rss-fetcher`
10. link the app to the redis database: `dokku redis:link rss-fetcher-backend-q rss-fetcher`
11. link the app to the postgres database: `dokku postgres:link rss-fetcher-db rss-fetcher`
13. link the app to the external storage directory: `dokku storage:mount rss-fetcher /var/lib/dokku/data/storage/rss-fetcher-daily-files:/app/storage`

### Release the worker app

1. setup the configuration on the dokku app: `dokku config:set rss-fetcher BROKER_URL=amqp://u:p@dokku-rabbitmq-rss-fetcher-q:5672/rss_fetcher_q BROKER_URL=BACKEND_URL=redis://u:p@dokku-redis-rss-fetcher-backend-q:6379 SENTRY_DSN=https://mydsn@sentry.io/123 DATABASE_URL=postgresql:///rss-fetcher MAX_FEEDS=10000 RSS_FILE_PATH=/app/storage SAVE_RSS_FILES=0`
2. add a remote: `git remote add prod dokku@prod.server.org:rss-fetcher`
3. scale it to get a worker (dokku doesn't add one by default): `dokku ps:scale rss-fetcher worker=1` (this might only work after the first deployment)

### Setup the fetcher to run automatically

1. Add a cron job to fetch during feeds during the day (every 30 mins): `*/30 * * * * /usr/bin/dokku run rss-fetcher fetcher /app/run-fetch-rss-feeds.sh >> /var/log/run-fetch-rss-feeds-cron.log 2>&1`
2. Add a cron job to generate RSS files once a day: `30 0 * * * /usr/bin/dokku run rss-fetcher generator /app/run-gen-daily-story-rss.sh >> /var/log/run-gen-daily-story-rss-cron.log 2>&1`

### Setup database backups

The local logging database is useful for future interrogation, so we back it up.

1. `dokku postgres:backup-auth rss-fetcher-db AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY`
2. `dokku postgres:backup-schedule rss-fetcher-db "0 1 * * *" mediacloud-rss-fetcher-backup`

Releasing
---------

1. When you make a change, edit `fetcher.VERSION` and update the `CHANGELOG.md` file with a note about what changed.
2. Commit and tag with the version number - ie "v1.1.1"
3. push the code to the server: `git push prod main`
