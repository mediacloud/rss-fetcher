#!/bin/sh

# install docker and dokku for backup-rss-fetcher
# written 2022-09-12 by Phil Budne under Ubuntu 22.04
# for (backup-)rss-fetcher development & test
# using tarbell.cs.umass.edu as a model.

# May not install packages/plugins needed for other Dokku apps.
# Your mileage may vary.

# written before I knew about
# https://raw.githubusercontent.com/dokku/dokku/vX.Y.Z/bootstrap.sh

SCRIPT_DIR=$(dirname $0)
COMMON_SH=$SCRIPT_DIR/common.sh
INSTANCE=ignored
if [ ! -f $COMMON_SH ]; then
    echo cannot find $COMMON_SH 1>&2
    exit 1
fi
. $COMMON_SH

check_root

RELEASE_NAME=$(lsb_release -cs 2>/dev/null)
if [ "x$RELEASE_NAME" = x ]; then
    echo could not get OS release 1>&2
    exit 1
fi

# fails for https://packagecloud.io/dokku/dokku/gpgkey 
#URL_GET="curl -sS"
URL_GET="wget -qO-"

_indir() {
    SFX=$1
    eval echo "\$${PFX}${SFX}"
}

NEED_APT_UPDATE=
# NOTE! apt-key deprecated (and due for removal after Ubuntu 22.04)
for SRC in $SOURCES; do
    # get prefix for environment variables for _indir
    PFX=$(echo "$SRC" | tr a-z A-Z)_

    LIST_FILE="$APT_SOURCES_LIST_D/$SRC.list"
    GPG_FILE="$APT_KEYRINGS_D/$SRC.gpg"
    GPG_URL=$(_indir GPG_URL)
    PKG_URL=$(_indir URL)

    # XXX expects freshly installed system: could be paranoid
    #	and grep $SRC /etc/apt/sources.list /etc/apt/sources.list.d/*
    if [ -f "$LIST_FILE" ]; then
	echo "found $LIST_FILE"
    else
	if $URL_GET $GPG_URL | gpg --dearmor > $GPG_FILE.tmp && mv $GPG_FILE.tmp $GPG_FILE; then
	    echo created $GPG_FILE
	    # creates /root/.gnupg
	    #gpg --show-keys < $GPG_FILE
	else
	    echo error creating $GPG_FILE from $GPG_URL
	    rm -f $GPG_FILE.tmp
	    exit 1
	fi
	COMPONENTS=$(_indir COMPONENTS)
	echo "deb [arch=amd64 signed-by=$GPG_FILE] $PKG_URL $RELEASE_NAME $COMPONENTS" > $LIST_FILE
	echo created $LIST_FILE:
	cat $LIST_FILE
	NEED_APT_UPDATE=1
	echo ''
    fi
done

if [ "x$NEED_APT_UPDATE" != x ]; then
    echo 'running apt update:'
    apt update
    echo ''
fi

# add any additional packages on next line
PREREQ='nginx'
apt install $PREPREQ

# _could_ loop for SOURCES again looking for THING_PACKAGES, but this
# seems sufficient.  Asks many questions (either figure out how to
# prevent, supply answers here, or run under "expect"?)
if dpkg -s dokku >/dev/null 2>&1; then
    echo dokku installed
else
    echo ==== apt install dokku
    echo 'NOTE!!! Answer YES to questions about nginx-vhosts and vhosts'
    apt install dokku
fi

# before installing letsencrypt?
#dokku domains:set-global $DOMAIN

for PLUGIN in postgres letsencrypt graphite; do
    if [ -d /var/lib/dokku/plugins/available/$PLUGIN ]; then
	echo found $PLUGIN plugin
    else
	echo ==== install dokku $PLUGIN plugin
	dokku plugin:install https://github.com/dokku/dokku-$PLUGIN.git $PLUGIN

	case $PLUGIN in
	letsencrypt)
	    true

	    # from https://www.freecodecamp.org/news/how-to-build-your-on-heroku-with-dokku/
	    #dokku config:set --global DOKKU_LETSENCRYPT_EMAIL=email@domain.com

	    # see also global domain setting above!!!

	    # adds "@daily dokku letsencrypt:auto-renew &>> /var/log/dokku/letsencrypt.log"
	    # to dokku user crontab (view with "crontab -u dokku -l")
	    # NOTE!!! Let's Encrypt REQUIRES that the domain you're asking for a cert for
	    # is Internal visible!!!
	    #dokku letsencrypt:cron-job --add
	    ;;
	esac
    fi
done
