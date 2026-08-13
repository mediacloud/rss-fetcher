Scripts for installing Dokku and creating one of three flavors of
rss-fetcher dokku app instance:

* production (app name rss-fetcher)
* staging (app name staging-rss-fetcher)
* development (app name USER-rss-fetcher)

# Files:

## deploy.py: deployment swiss army knife using mc-deploy
	subcommands:
	* clone INSTANCE - clone production database to INSTANCE db
	* create INSTANCE - create app instance
	* dburl INSTANCE - return Dokku DATABASE_URL for use outside dokku
	* deploy - push branch to Dokku
	* destroy INSTANCE - destroy an app instance

	where INSTANCE is prod, staging, USER

deploy.py -h gives help on subcommands and base options:

```
usage: deploy [-h] [-d] [--ignore-no-changes] [-n] [-T {prod,staging}] [-H HOST]
              {clone,create,dburl,deploy,destroy,dokku-version,push,version} ...

positional arguments:
  {clone,create,dburl,deploy,destroy,dokku-version,push,version}
                        command
    clone               Clone production database for dev/staging
    create              Create Dokku app instance
    dburl               Return DATABASE_URL for local use outside Dokku ie; `export
                        DATABASE_URL=$(..../deploy.py dburl dev/prod/USER)`
    deploy              Push code to Dokku app instance
    destroy             Destroy Dokku app instance
    dokku-version       test ssh key, display dokku version
    push                (pointer to deploy)
    version             Display deployment package version

options:
  -h, --help            show this help message and exit
  -d, --debug           debug deployment code
  --ignore-no-changes   continue dry-run if no code or config changes
  -n, --no-action       dry run: take no actions
  -T {prod,staging}, --test {prod,staging}
                        test deployment code (impl. --dry-run)
  -H HOST, --host HOST  Dokku server to deploy to (default ifill.angwin)
```

And each subcommand takes `-h` as an option to display
subcommand specific options and arguments

## test-feeds.psql: postgres commands to reset feeds (but not stories
	or fetch_events) to a small number of test cases
	(PB: I use this in my home test environment and in my
	pbudne-rss-fetcher dokku instance)

After cloning the production database it's HIGHLY recommended that you
manually disable most feeds by running (for varying values of N):

	```
	ssh -t dokku@$(hostname) postgres:connect INSTANCE-rss-fetcher
	update feeds set active = FALSE where id < N;
	\q
	```

	(PB: I do this for staging, with N = 100000, for development
	use a smaller value (1000) or the test-feeds.psql file above).

# auxillary scripts (move to system-dev-ops repo!!!)

* create-stats.sh: create monitoring service (not used in a LONG time!)
* stats-service-proxy.sh: create proxy for letsencrypt; called by create-stats.sh
* install-dokku.sh: install dokku on system (must be run as root)
* uninstall-dokku.sh: remove dokku from system (must be run as root)
* http-proxy.sh: run on an Internet visible server to create an https proxy
	to an app (or other plaintext http server) running on ANOTHER
	server that is NOT Internet visible.
