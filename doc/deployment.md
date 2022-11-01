Deploying
=========

This is built to deploy via a PaaS host, like Heroku. We deploy via [dokku](https://dokku.com).

If you are debugging locally, copy `.env.template` to `.env` and edit as needed.

To create a dokku instance:
`./dokku-scripts/instance create NAME`

where NAME is one of prod, staging, dev-USERNAME

For prod and staging, you must have a .prod file with
`SENTRY_DSN=https://xxxxxxxxxxxxx@xxx.ingest.sentry.io/xxxxxx`

### Setup database backups

The local logging database is useful for future interrogation, so we back it up.

1. `dokku postgres:backup-auth rss-fetcher-db AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY`
2. `dokku postgres:backup-schedule rss-fetcher-db "0 1 * * *" mediacloud-rss-fetcher-backup`

Releasing
---------

1. When you make a change, edit `fetcher.VERSION` and update the `CHANGELOG.md` file with a note about what changed.
2. Commit and tag with the version number - ie "v1.1.1"
3. check out the prod (or staging) branch
4. git merge working_branch; git push (or merge via github pull request and do "git pull")
6. ./dokku-scripts/push.sh
