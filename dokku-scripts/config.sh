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

################
# before taking any actions:

if public_server; then
    # not in global config on tarbell:
    add_vars DOKKU_LETSENCRYPT_EMAIL=$DOKKU_LETSENCRYPT_EMAIL
fi

# used in fetcher/__init__.py to set APP
# ('cause I didn't see it available any other way -phil)
add_vars MC_APP=$APP

# before VF, to allow override??
if [ "x$TYPE_OR_UNAME" = xprod ]; then
    # production only settings:
    # XXX want 60? 90??
    add_vars RSS_OUTPUT_DAYS=30
fi

case "$TYPE_OR_UNAME" in
prod|staging)
    # XXX maybe use .$TYPE (.staging vs .prod) file??
    # could get from "vault" file if using ansible.
    VARS_FILE=.prod
    VF=$TMP
    # get vars for count, and to ignore comment lines!
    egrep '^(SENTRY_DSN|RSS_FETCHER_(USER|PASS))=' $VARS_FILE > $VF
    if [ $(wc -l < $VF) != 3 ]; then
	echo "Need $VARS_FILE file w/ SENTRY_DSN RSS_FETCHER_{USER,PASS}" 1>&2
	exit 1
    fi
    WORKERS=16
    ;;
*)
    UNAME=$TYPE_OR_UNAME
    VF=.pw.$UNAME
    if [ -f $VF ]; then
	echo using rss-fetcher API user/password in $VF
    else
	# XXX _could_ check .env file (used for non-dokku development)
	# creating from .env.template
	# and adding vars if needed.
	echo generating rss-fetcher API user/password, saving in $VF
	echo RSS_FETCHER_USER=$UNAME$$ > $VF
	echo RSS_FETCHER_PASS=$(openssl rand -base64 15) >> $VF
    fi
    #chown $UNAME $VF
    ;;
esac
add_vars $(cat $VF)

if [ "x$WORKERS" != x ]; then
    add_vars RSS_FETCH_WORKERS=$WORKERS
fi

################################################################
# set config vars
# make all add_vars calls before this!!!

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
