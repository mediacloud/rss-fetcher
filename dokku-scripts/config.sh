#!/bin/sh
# helper to set dokku app config: called from push.sh
# XXX check non-empty!
APP=$1

if [ "x$APP" = x ]; then
    echo Usage: $0 DOKKU_APP_NAME 1>&2
    exit 1
fi

# XXX check app exists?

# get from command line options?
CONFIG_OPTIONS=--no-restart

################
SCRIPT_DIR=$(dirname $0)
INSTALL_CONF=$SCRIPT_DIR/install-dokku.conf
if [ ! -f $INSTALL_CONF ]; then
    echo cannot find $INSTALL_CONF 1>&2
    exit 1
fi
. $INSTALL_CONF

TMP=/tmp/dokku-config-$$
trap "rm -f $TMP" 0
touch $TMP
chmod 600 $TMP

################

DATABASE_SVC=$(app_to_db_svc $APP)

case $APP in
rss-fetcher) TYPE_OR_UNAME=prod;;
staging-rss-fetcher) TYPE_OR_UNAME=staging;;
*) TYPE_OR_UNAME=$(echo $APP | sed 's/-rss-fetcher//');;
esac

################
# set config vars:

add_vars() {
    VARS="$VARS $*"
}

# set dokku timeout values to half the default values:
# WISH: stop all processes before launching new ones?!

add_vars DOKKU_WAIT_TO_RETIRE=30
add_vars DOKKU_DEFAULT_CHECKS_WAIT=5

# display/log time in UTC:
add_vars TZ=UTC

# used by queue_feeds w/o --loop argument:
# XXX obsolete
add_vars MAX_FEEDS=15000

################
# "postgres:" URLs deprecated in SQLAlchemy 1.4
# NOTE: sqlalchemy 2.0 + psycopg3 wants postgresql+psycopg:
#	(currently handled by fix_database_url() function)

DATABASE_URL=$(dokku postgres:info $DATABASE_SVC --dsn | sed 's@^postgres:@postgresql:@')
add_vars DATABASE_URL=$DATABASE_URL

################
# fetcher related vars

#add_vars SAVE_RSS_FILES=0

################

# using automagic STATSD_URL in fetcher/stats.py

STATSD_PREFIX="mc.${TYPE_OR_UNAME}.rss-fetcher"
add_vars STATSD_PREFIX=$STATSD_PREFIX

################################################################
# set config vars
# make all add_vars calls before this!!!

# config:set causes redeployment, so check first
dokku config:show $APP | tail -n +2 | sed 's/: */=/' > $TMP
NEED=""
# loop for var=val pairs
for VV in $VARS; do
    # VE var equals
    VE=$(echo $VV | sed 's/=.*$/=/')
    # find current value
    CURR=$(grep "^$VE" $TMP)
    if [ "x$VV" != "x$CURR" ]; then
	NEED="$NEED $VV"
    fi
done

if [ "x$NEED" != x ]; then
    echo setting dokku config: $NEED
    dokku config:set $CONFIG_OPTIONS $APP $NEED
else
    echo no dokku config changes
fi
