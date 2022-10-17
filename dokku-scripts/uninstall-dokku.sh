#!/bin/sh

# Phil Budne, September 2022
echo 'NOTE! NOT TESTED'

SCRIPT_DIR=$(dirname $0)
INSTALL_CONF=$SCRIPT_DIR/install-dokku.conf
if [ ! -f $INSTALL_CONF ]; then
    echo cannot find install.conf 1>&2
    exit 1
fi
. $INSTALL_CONF

check_root

dokku letsencrypt:cron-job --remove

# XXX reverse items in SOURCES!! and remove via NAME_PACKAGES??
apt-get remove dokku
apt-get autoremove

# remove package repositories/keys
for SRC in $SOURCES; do
    rm -f $APT_SOURCES_LIST_D/$SRC.list $APT_KEYRINGS_D/$SRC.gpg
done
