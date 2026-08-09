Scripts for installing Dokku and creating one of three flavors of
rss-fetcher dokku app instance:

* production (app name rss-fetcher)
* staging (app name staging-rss-fetcher)
* development (app name USER-rss-fetcher)

# SCRIPTS:

* common.sh: (not a script) shared code/config sourced by scripts
	vars can be overridden by adding a local.sh file to this directory.

* install-dokku.sh: install dokku on system (must be run as root)

* uninstall-dokku.sh: remove dokku from system (must be run as root)

* deploy.py: has multiple functions:
  + `create INSTANCE`
	create an empty dokku app
  + `clone INSTANCE`
	clone the production app database to INSTANCE
  + `deploy`
	push the currently checked out branch to Dokku.
  + `dburl INSTANCE`
	returns postgres URL for a dokku postgres service suitable
	for use on dokker host as DATABASE_URL environment/.env config
	(for testing/debugging a script against a dokku database).
  + `destroy INSTANCE`
	destroy a dokku app

where INSTANCE is prod, staging or USER

* http-proxy.sh: run on an Internet visible server to create an https proxy
	to an app (or other plaintext http server) running on ANOTHER
	server that is NOT Internet visible.

* test-feeds.psql: postgres commands to reset feeds (but not stories
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

# auxillary scripts:

(scripts called by other scripts)

* create-stats.sh: create monitoring service; called by instance.sh
* stats-service-proxy.sh: create proxy for letsencrypt; called by create-stats.sh
