This is built to deploy via a PaaS host, like Heroku. We deploy via [dokku](https://dokku.com).

NOTE!! The top level autopep8.sh and mypy.sh scripts should be run
before merging to mediacloud/main branch!  (mypy.sh creates a local
venv, autopep8.sh expects autopep8 be installed)

See [../dokku-scripts/README.md](dokku-scripts/README.md) for descriptions
of all the dokku helper scripts.

Development
===========

If you are debugging locally, copy `.env.template` to `.env` and edit as needed.

To install dokku, run `.../dokku-scripts/install-dokku.sh` as root.

To test under dokku, first create a development dokku instance by running (as root)

   ```
   .../dokku-scripts/instance.sh create dev-MYUSERNAME
   ```

This will also add a git "remote" used later by `push.sh` to deploy the code.

creates an application named `MYUSERNAME-rss-fetcher` and a `dokku-graphite` plugin instance visible
as `http://stats.SERVERNAME`

Check your code into a git branch (named something other than
`staging` or `prod`, push to your github `origin`, then run

    ```
    .../dokku-scripts/push.sh
    ```

to deploy the code (by doing a git push to the app server git repo).
`push.sh` will apply and push a tag like `YYYY-MM-DD-HH-MM-SS-HOSTNAME-APPNAME`

The application container `/app/storage` directory
appears on the host system in `/var/lib/dokku/data/storage/APPNAME`,
including `logs`, `rss-output-files` and `db-archive` directories.

*TEXT HERE ABOUT POPULATING FEEDS TABLE* (clone from production???)

If your devlopment instance is on a private network, you can make the
Grafana server created by `instance.sh` on Internet visible server
`BASTIONSERVER.DO.MA.IN` using `dokku-scripts/http-proxy.sh` which can
create a proxy application named `stats.YOURSERVER` which should be
Internet visible service at
`https://stats.YOURSERVER.BASTIONSERVER.DO.MA.IN` (assuming there is a
wildcard DNS address record for `*.BASTIONSERVER.DO.MA.IN`.

*TEXT HERE ABOUT POPULATING A GRAFANA DASHBOARD*

*TEXT HERE ABOUT ACCEPTANCE CRITERIA!!*

Your development application can be disposed of by running

    `dokku-scripts/instance.sh destroy dev-MYUSERNAME`


Staging
=======

Once you are ready to deploy your code, and your changes have been
merged into the github mediacloud account "main" branch, the next step
is to run the code undisturbed in a staging app instance:

If a staging instance does not exist (or instance.sh has been changed):

   ```
   ./dokku-scripts/instance.sh create staging
   ```

Which will create an application named `staging-rss-fetcher`
(or modify an existing one to current spec).

*TEXT HERE ABOUT FEEDS AND STORIES TABLES* (clone from production???)*

Then merge the state of the mediacloud/main branch into
mediacloud/staging, either via github PR or `git checkout staging; git
merge main`

*The staging branch should ONLY be updated by merges/pulls from main.*

You must have a `.prod` file with a line:
`SENTRY_DSN=https://xxxxxxxxxxxxx@xxx.ingest.sentry.io/xxxxxx`
pointing to the mediacloud sentry.io URL (events will be sent with
environment=staging).

Then, with the staging branch checked out (and pushed to both "origin"
and to the mediacloud account staging branch), again run:

    ```
    .../dokku-scripts/push.sh
    ```

again, `push.sh` will apply and push a tag: `YYYY-MM-DD-HH-MM-SS-HOSTNAME-staging-rss-fetcher`

*TEXT HERE ABOUT ACCEPTANCE CRITERIA!!*

Production
==========

Once the code has been running stably without modification in staging,
it can be deployed to production.

Once again, `instance.sh` can be used to create a production application instance
(or modifiy an existing one to current specifications, and install a stats server):

   ```
   ./dokku-scripts/instance.sh create prod
   ```

When you are ready to make a release, edit `fetcher/__init__.py` and
update `VERSION` and update the `CHANGELOG.md` file with a note about
what changed, and merge the change to the staging branch
(and test in staging if ANY other changes were made).

*The "prod" branch should ONLY be changed by merging from the "staging" branch.*

Merge the mediacloud account staging branch into the prod branch, and run `push.sh`

`push.sh` should check whether a `vVERSION` tag exists (and exit if it
does), otherwise it creates and pushes the tag.

### Setup database backups

The production postgres database is backed up to AWS S3:

1. `dokku postgres:backup-auth rss-fetcher-db AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY`
2. `dokku postgres:backup-schedule rss-fetcher-db "0 1 * * *" mediacloud-rss-fetcher-backup`

* TEXT HERE ABOUT SETTING UP BACKUP OF db-archive *
