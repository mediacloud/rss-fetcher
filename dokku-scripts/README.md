Scripts for installing Dokku and creating one of three flavors of
rss-fetcher dokku app instance:

* production (app name rss-fetcher)
* staging (app name staging-rss-fetcher)
* development (app name USER-rss-fetcher)

SCRIPTS:

* install.conf -- shared config for [un]install-dokku.sh 

* install-dokku.sh -- install dokku on system (must be run as root)
	MUST be run as ./install-dokku.sh to find install.conf

* uninstall-dokku.sh -- remove dokku from system (must be run as root)
	MUST be run as ./install-dokku.sh to find install.conf

* fetcher-instance.sh (must be run as root) create a dokku app instance
	takes arguments: create|destroy prod|staging|dev-USER

* fetcher-push.sh: push current repository to dokku app instance
	based on current branch name (branch must be "clean")

NOTA BENE!!

* Have not tested running more than one app instance at a time!

* Does not (yet) enable "letsencrypt" crontab -- needs configuration
	for Internet visible domain (grep for DOMAIN),
	and DOKKU_LETSENCRYPT_EMAIL
