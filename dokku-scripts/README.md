Scripts for installing Dokku and creating one of three flavors of
rss-fetcher dokku app instance:

* production (app name rss-fetcher)
* staging (app name staging-rss-fetcher)
* development (app name USER-rss-fetcher)

SCRIPTS:

* install.conf -- shared config for scripts

* install-dokku.sh -- install dokku on system (must be run as root)

* uninstall-dokku.sh -- remove dokku from system (must be run as root)

* instance.sh (must be run as root) create a dokku app instance
	takes arguments: create|destroy prod|staging|dev-USER

	+ Can be re-run at any time to re-configure an app
	+ Script SHOULD be updated to include new changes!!!

* push.sh: push current repository to dokku app instance
	based on current branch name (branch must be "clean")

* http-proxy.sh: run on an Internet visible service to create an https proxy
	to an app (or other plaintext http server) running on a
	server that is not Internet visible.

auxillary scripts
-----------------

* create-stats.sh -- create monitoring service; called by instance.sh
* stats-service-proxy.sh -- create proxy for letsencrypt; called by create-stats.sh
