#!/bin/sh

echo 'NOTE! NOT TESTED'
if [ `whoami` != root ]; then
    echo must be run as root 1>&2
    exit 1
fi

SCRIPT_DIR=$(dirname $0)
INSTALL_CONF=$SCRIPT_DIR/install-dokku.conf
if [ ! -f $INSTALL_CONF ]; then
    echo cannot find install.conf 1>&2
    exit 1
fi
. $INSTALL_CONF

LOCAL_CONF=$SCRIPT_DIR/local-dokku.conf
if [ -f $LOCAL_CONF ]; then
    . $LOCAL_CONF
fi

dokku letsencrypt:cron-job --remove

# XXX reverse items in SOURCES!! and remove via NAME_PACKAGES??
apt-get remove dokku
apt-get autoremove

# remove package repositories/keys
for SRC in $SOURCES; do
    rm -f $APT_SOURCES_LIST_D/$SRC.list $APT_KEYRINGS_D/$SRC.gpg
done
