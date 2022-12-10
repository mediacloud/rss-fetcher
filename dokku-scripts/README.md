Scripts for installing Dokku and creating one of three flavors of
rss-fetcher dokku app instance:

* production (app name rss-fetcher)
* staging (app name staging-rss-fetcher)
* development (app name USER-rss-fetcher)

# SCRIPTS:

* install.conf: (not a script) shared config for scripts
	can be overridden by adding a local-dokku.conf file to this directory.

* install-dokku.sh: install dokku on system (must be run as root)

* uninstall-dokku.sh: remove dokku from system (must be run as root)

* instance.sh: create a dokku app instance
	+ takes arguments: create|destroy prod|staging|dev-USER
	+ MUST be run as root
	+ Can be re-run at any time to re-configure an app
	+ Script SHOULD be updated to include new config changes!!!

* push.sh: push current repository to dokku app instance
	based on current branch name (branch must be committed and pushed)

* http-proxy.sh: run on an Internet visible server to create an https proxy
	to an app (or other plaintext http server) running on ANOTHER
	server that is NOT Internet visible.

* clone-db.sh: clone one instance's database to another instance;
	Afterwards it's HIGHLY recommended that you manually disable most
	feeds by running:

	ssh -t dokku@$(hostname) postgres:connect INSTANCE-rss-fetcher
	update feeds set active = FALSE where id < 1000;
	\q

# auxillary scripts:

* create-stats.sh: create monitoring service; called by instance.sh
* stats-service-proxy.sh: create proxy for letsencrypt; called by create-stats.sh
