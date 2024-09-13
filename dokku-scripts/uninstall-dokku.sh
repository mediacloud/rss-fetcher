#!/bin/sh

# Phil Budne, September 2022
echo 'NOTE! NOT TESTED'

SCRIPT_DIR=$(dirname $0)
COMMON_SH=$SCRIPT_DIR/common.sh
INSTANCE=ignored
if [ ! -f $COMMON_SH ]; then
    echo cannot find $COMMON_SH 1>&2
    exit 1
fi
. $COMMON_SH

check_root

dokku letsencrypt:cron-job --remove

# XXX reverse items in SOURCES!! and remove via NAME_PACKAGES??
apt-get remove dokku
apt-get autoremove

# remove package repositories/keys
for SRC in $SOURCES; do
    rm -f $APT_SOURCES_LIST_D/$SRC.list $APT_KEYRINGS_D/$SRC.gpg
done
