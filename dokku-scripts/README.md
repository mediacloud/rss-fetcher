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

* instance.sh: create a dokku app instance
	+ takes arguments: create|destroy prod|staging|USER
	+ Can be re-run at any time to re-configure an app
	+ Script SHOULD be updated to include new config changes!!!
	+ Dokku app/service names created:
	   * "prod" creates "rss-fetcher" (app, plus postgres and redis services)
	   * "staging" creates "staging-rss-fetcher"
	   * "dev-USER" creates "USER-rss-fetcher"

* push.sh: push current repository to dokku app instance
	based on current branch name (branch must be committed and pushed)

* http-proxy.sh: run on an Internet visible server to create an https proxy
	to an app (or other plaintext http server) running on ANOTHER
	server that is NOT Internet visible.

* test-feeds.psql: postgres commands to reset feeds (but not stories
	or fetch_events) to a small number of test cases
	(PB: I use this in my home test environment and in my
	pbudne-rss-fetcher dokku instance)

* clone-db.sh: clone one instance's database to another instance;
	Afterwards it's HIGHLY recommended that you manually disable most
	feeds by running (for varying values of N):

	```
	ssh -t dokku@$(hostname) postgres:connect INSTANCE-rss-fetcher
	update feeds set active = FALSE where id < N;
	\q
	```

	(PB: I do this for staging, with N = 100000, for development
	use a smaller value (1000) or the test-feeds.psql file above).

* dburl.sh: returns postgres URL for a dokku postgres service suitable
	for use on dokker host as DATABASE_URL environment/.env config
	(for testing/debugging a script against a dokku database).

# auxillary scripts:

(scripts called by other scripts)

* create-stats.sh: create monitoring service; called by instance.sh
* stats-service-proxy.sh: create proxy for letsencrypt; called by create-stats.sh
