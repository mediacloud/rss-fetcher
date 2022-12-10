This is built to deploy via a PaaS host, like Heroku.
We deploy via [dokku](https://dokku.com).

NOTE!! The top level autopep8.sh and mypy.sh scripts should be run
before merging code to mediacloud/main branch!  It's probably best to
run autopep8.sh before every commit; mypy.sh creates a local venv (in
directory "venv" with all the necessaries to run mypy, and to run the
code).  autopep8.sh expects autopep8 be installed.

There are a number of shell scripts to help deploy the app (for both
testing and production); See
[../dokku-scripts/README.md](../dokku-scripts/README.md) for
descriptions.

# Rationale

This document describes an orthodox priestly ritual for the deployment
of a critical service.

	And Saint Attila raised the hand grenade up on high, saying,

		'O Lord, bless this thy hand grenade, that with it thou mayst
		blow thine enemies to tiny bits, in thy mercy.'

	And the Lord spake, saying:
		'First shalt thou take out the Holy Pin.

		Then shalt thou count to three, no more, no less.

		Three shall be the number thou shalt count,
		and the number of the counting shall be three.
    
		Four shalt thou not count, neither count thou two,
		excepting that thou then proceed to three.
    
		Five is right out.
		
		Once the number three, being the third number, be
		reached, then lobbest thou thy Holy Hand Grenade of
		Antioch towards thy foe, who, being naughty in My
		sight, shall snuff it.'
    
	Armaments, chapter 2, verses 9-21
		Monty Python and the Holy Grail

# Development

DO YOUR DEVELOPMENT ON A GIT BRANCH!

## local development

If you are debugging locally, copy `.env.template` to `.env`
(you may not need to edit it).

Running ./mypy.sh will construct a virtual environment with all necessary
components.

NOTE!  Installing the psycopg2 DBI may require postgres client
libraries (ubuntu package name here) to be installed.

After running `mypy.sh`, type `. ./venv/bin/activate`

You will also need a postgres server, and a redis server.

Various `run-....` scripts are in the top level directory, see
`Procfile` for how/when they're invoked.

All python scripts take uniform logging command line options,
and append to a log file `storage/logs/SCRIPTNAME.pid.NNNN.log`

### local postgres setup notes

After installing the postgresql server package(s):

To add yourself as a postgres user:

	sudo -u postgres createuser -s MY_USER_NAME

Then, (as yourself) to create an rss-fetcher database:

	createdb rss-fetcher

## development/test under Dokku

To install dokku on a mediacloud server (on Ubuntu 22.04),
run `.../dokku-scripts/install-dokku.sh` as root.

To test under dokku, first create a development dokku instance by running (as root)

   .../dokku-scripts/instance.sh create dev-USERNAME

Creates an application named `USERNAME-rss-fetcher`, and
dokku-postgres and dokku-redis services with the same name, and
installs a crontab as /etc/cron.d/APPNAME.  If there isn't already a
local dokku-graphite service running, it creates one visible as
`http://stats.SERVERNAME`.

It also checks if USERNAME's ssh public key is installed for the dokku
user, so they can add `alias dokku=ssh dokku@$(hostname)` to their
`.bashrc` file.

instance.sh also adds a git remote named dokku_USERNAME (pointing to
the local dokku account) to the repository, for use by push.sh.

You can duplicate the production database into your Dokku development
environment by running `./dokku-scripts/clone-db.sh USERNAME-rss-fetcher`

Check your code into a git branch (named something other than
`staging` or `prod`, push to your github `origin` (eg a github clone
of the project under your account, or a branch in the mediacloud
account) then run:

    ./dokku-scripts/push.sh

to deploy the code. `push.sh` will apply and push a tag
like `YYYY-MM-DD-HH-MM-SS-HOSTNAME-USERNAME-rss-fetcher`.

NOTE: push.sh is run as a regular user (no sudo required).

The application container `/app/storage` directory
appears on the host system in `/var/lib/dokku/data/storage/APPNAME`,
and includes `logs`, `rss-output-files` and `db-archive` subdirectories.

Under dokku, All top level scripts append to a log file
`storage/logs/SCRIPTNAME.DYNO.log` (where DYNO is PROGRAM.N).

If your devlopment instance is on a private network (ie; an internal
system in the angwin cluster), you can make the Grafana server created
by `instance.sh` on Internet visible server `BASTIONSERVER.DO.MA.IN`
using `dokku-scripts/http-proxy.sh` which can create a proxy
application named `stats.YOURSERVER` which should be Internet visible
service at `https://stats.YOURSERVER.BASTIONSERVER.DO.MA.IN` (assuming
there is a wildcard DNS address record for `*.BASTIONSERVER.DO.MA.IN`.

*TEXT HERE ABOUT POPULATING A GRAFANA DASHBOARD*

*TEXT HERE ABOUT ACCEPTANCE CRITERIA!!*
(including mypy.sh running cleanly, and running autopep8.sh)
Talk about pytest tests???

NOTE! If you've changed the crontab or changed or added any config
parameters, be sure they're reflected in `dokku-scripts/instance.sh`
(and note in CHANGELOG.md that instance.sh needs to be re-run before
installation).

If you've changed a script that's run from the crontab, it's good to wait
(either here, or in staging) to see that it runs correctly from a crontab.

When the acceptance criteria have been met, the code can be advanced to staging.

At this point edit `fetcher/__init__.py` and update `VERSION` and
make sure `CHANGELOG.md` is up to date, and commit to the "main" branch.

     Digression: Updating CHANGELOG.md on every commit is common
     practice, BUT it's frequently a source of merge/rebase lossage
     when multiple developers are active.

If "main" and "staging" are otherwise identical, merge main into
staging.  If "staging" is the result of cherry-picking, cherry-pick
the version change commit into "staging"

Your development application can be disposed of by running

    dokku-scripts/instance.sh destroy dev-USERNAME

(you will be prompted to enter USERNAME-rss-fetcher at a number of
points). Or, to stop all application processes (leaving the database
running):

    dokku ps:stop USERNAME-rss-fetcher

# Staging

The purpose of the staging step is to test deployment of the code
EXACTLY as it will be deployed in production.

Once you are ready to deploy your code, and your changes have been
merged into the github mediacloud account "main" branch, the next step
is to run the code undisturbed in a staging app instance:

If a staging instance does not exist (or instance.sh has been changed),
as root, run:

   ./dokku-scripts/instance.sh create staging

Which will create a Dokku application named `staging-rss-fetcher` (or
modify an existing one to current spec).  A staging environment can be
run on ANY server.

You can duplicate the production database into your staging
environment by running `./dokku-scripts/clone-db.sh staging-rss-fetcher`

This is best done while there are no active staging-rss-fetcher
containers running (ie; before pushing code, or after executing
`dokku ps:stop staging-rss-fetcher`)

Then merge the state of the mediacloud/main branch into
mediacloud/staging, either via github PR or `git checkout staging; git
merge main`.  If only selected commits in the main branch can be
deployed, you can cherry-pick them into the staging branch.

**The staging branch should ONLY be updated by merges/pulls/cherry-picks from main.**

*Thou shalt not commit changes directly to the staging branch, and only
changes in the main branch shall be advanced to staging.  This ensures
that no "last minute fixes" escape capture.*

You must have a `.prod` file with a line:
`SENTRY_DSN=https://xxxxxxxxxxxxx@xxx.ingest.sentry.io/xxxxxx`
pointing to the mediacloud sentry.io URL (events will be sent with
environment=staging).

Then, with the staging branch checked out (and pushed to the
mediacloud account staging branch), run:

    ./dokku-scripts/push.sh

Again, `push.sh` will apply and push a tag: `YYYY-MM-DD-HH-MM-SS-HOSTNAME-staging-rss-fetcher`

*TEXT HERE ABOUT ACCEPTANCE CRITERIA!!*

When the acceptance criteria have been met, the code can be moved to
production.  If ANY problems are discovered in staging, fixes MUST be
committed to "main", pulled or picked to staging and tested first.

# Production

Once the code has been running stably without modification in staging,
it can be deployed to production (ANY changes must be made first in
main, then tested in staging before moving to production).

Once again, `instance.sh` can be used to create a production application instance
(or modifiy an existing one to current specifications, and install a stats server):

   ./dokku-scripts/instance.sh create prod

(and re-test in staging if ANY other changes were made).

**The "prod" branch should ONLY be changed by merging from the "staging" branch.**

*(Thou shalt not commit changes directly to the prod or staging branches).*

Merge the mediacloud account staging branch into the prod branch, and
with the prod branch checked out, run `push.sh`

`push.sh` checks whether a `vVERSION` tag already exists (and exits if it
does), otherwise it applies and pushes the tag.

### Setup database backups

When the `./dokku-scripts/instance.sh create prod` command above is
run it will schedule backups of postgres (via `dokku
postgres:backup-schedule` which writes `/etc/cron.d/dokku-postgres-rss-fetcher`),
and other directories to AWS S3 (via `/etc/cron.d/rss-fetcher`).

Backup user's `~/.aws/credentials` file (which will be pre-populated
the necessary sections if not already present: the keys must be added
by hand!):

<table>
<tr><th>credentials file section<th>from /app/storage subdir<th>to S3 bucket/prefix<th>required AWS key policy
<tr><td>rss-fetcher-backup<td>db-archive<td>...-rss-fetcher-backup<td>...-web-tools-db-backup-get-put-delete
<tr><td>rss-fetcher-rss<td>rss-output-files<td>...-public/backup-daily/rss<td>...-public-get-put-delete
</table>

The key used for the `rss-fetcher-backup` section above also needs to be incanted as follows:

    dokku postgres:backup-auth rss-fetcher-db AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY

to authorize the deposit of postgres backups to S3.
