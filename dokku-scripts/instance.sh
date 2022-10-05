#!/bin/sh

# create or destroy an rss-fetcher dokku instance
# takes two arguments: action and type
# action: create or destroy
# type: prod, staging, or dev-UNAME
#	(UNAME must be a user in passwd file)

if [ `whoami` != root ]; then
    echo "$0 must be run as root" 1>&2
    exit 1
fi

OP="$1"
NAME="$2"

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

TYPE="$OP"
TYPE_OR_UNAME="$TYPE"
case "$OP" in
create|destroy)
    case "$NAME" in
    prod) PREFIX='';;
    staging) PREFIX='staging-';;
    dev-*) UNAME=$(echo "$NAME" | sed 's/^dev-//')
	   PREFIX="${UNAME}-"
	   TYPE=user
	   TYPE_OR_UNAME="$UNAME"
	   ;;
    *) ERR=1;;
    esac
    ;;
*) ERR=1;
esac

if [ "x$ERR" != x ]; then
    echo "usage: $0 create|destroy NAME" 1>&2
    echo "    where NAME is 'prod', 'staging' or 'dev-USERNAME'" 1>&2
    exit 1
fi

APP=${PREFIX}rss-fetcher

# Service names: Naming generically (instead of backend/broker)
# because can use redis for both. Generated docker container names are
# dokku.{postgres,redis,rabbitmq}.APP
REDIS_SVC=$APP
RABBITMQ_SVC=$APP
DATABASE_SVC=$APP

# storage for generated RSS files:
DAILY_FILES=${APP}-daily-files
# DAILY_FILES mount point inside container:
RSS_FILE_PATH=/app/storage

# XXX add storage for logs???

# server log directory for scripts run via "dokku run"
LOGDIR=/var/log/dokku/apps/$APP
LOGROTATE=/etc/logrotate.d/$APP
# letters and dashes only:
CRONTAB=/etc/cron.d/$APP

if [ "x$OP" = xdestroy ]; then
    # XXX make into a destroy function so can be used for teardown in case create fails??
    if ! dokku apps:exists $APP >/dev/null 2>&1; then
	echo app $APP not found 1>&2
	exit 1
    fi

    # destroy commands ask for confirmation: bug or feature??
    # (add --force to suppress??)

    dokku apps:destroy $APP
    if [ "x$TYPE" != user ]; then
	dokku rabbitmq:destroy $RABBITMQ_SVC
    fi
    dokku redis:destroy $REDIS_SVC
    dokku postgres:destroy $DATABASE_SVC

    rm -f $CRONTAB $LOGROTATE
    rm -rf $LOGDIR
    ## end destroy function

    exit 0
fi

if dokku apps:exists $APP >/dev/null 2>&1; then
    echo ERROR: app $APP exists 1>&2
    exit 1
fi

################
# before taking any actions

if [ "x$TYPE" = xprod ]; then
    if grep ^SENTRY_DSN .prod >/dev/null; then
	VARS="$VARS $(cat .prod)"
    else
	echo "Need .prod file w/ SENTRY_DSN" 1>&2
	exit 1
    fi
fi

################ ssh key management

if [ "x$UNAME" = x ]; then
    # production & staging: add logged-in user's key
    UNAME=$(who am i | awk '{ print $1 }')
    echo using user $UNAME for ssh key
fi

HOMEDIR=$(eval echo ~$UNAME)
if [ "x$HOMEDIR" = x -o ! -d "$HOMEDIR" ]; then
    echo could not find home directory for $UNAME 1>&1
    if [ "x$TYPE" = xuser ]; then
	exit 1
    fi
elif [ -d $HOMEDIR/.ssh ]; then
    # could be id_{rsa,dsa,ecdsa,ed25519,xmss,xmss-cert}.pub (etc?)
    # likely to work in the simple case (just one file present)
    for FILE in $HOMEDIR/.ssh/*.pub; do
	if [ -f $FILE ]; then
	    PUBKEY_FILE="$FILE"
	    echo found public key $PUBKEY_FILE
	    break
	fi
    done
    if [ "x$PUBKEY_FILE" = x ]; then
	echo "no pubkey found for $UNAME"
	# maybe generate one for the user???
    fi
fi

################

dokku apps:create $APP
# XXX check status & exit on failure?

################

if dokku redis:exists $REDIS_SVC >/dev/null 1>&2; then
    echo "redis $REDIS_SVC exists?"
else
    dokku redis:create $REDIS_SVC
    # XXX check status & call destroy on failure?
fi
dokku redis:link $REDIS_SVC $APP

REDIS_URL=$(dokku redis:info $REDIS_SVC --dsn)
VARS="$VARS BACKEND_URL=$REDIS_URL"

# NOTE!! celery backends need periodic cleanups run!

################

if [ "x$TYPE" = xuser ]; then
    # use redis based queue for developers

    BROKER_URL="$REDIS_URL/1"
else
    dokku rabbitmq:create $RABBITMQ_SVC
    # XXX check status & call destroy on failure?
    dokku rabbitmq:link $RABBITMQ_SVC $APP

    BROKER_URL=$(dokku rabbitmq:info $RABBITMQ_SVC --dsn)
fi
VARS="$VARS BROKER_URL=$BROKER_URL"

VARS="$VARS MAX_FEEDS=15000"

################

if dokku postgres:exists $DATABASE_SVC >/dev/null 1>&2; then
    echo "postgres $DATABASE_SVC exists?"
else
    dokku postgres:create $DATABASE_SVC
    # XXX check status & call destroy on failure?
fi
# postgres: URLs deprecated in SQLAlchemy 1.4
DATABASE_URL=$(dokku postgres:info $DATABASE_SVC --dsn | sed 's@^postgres:@postgresql:@')
VARS="$VARS DATABASE_URL=$DATABASE_URL"

dokku postgres:link $DATABASE_SVC $APP

################
# worker related vars

# XXX ensure, mount directory for worker logs???

dokku storage:ensure-directory $DAILY_FILES
dokku storage:mount $APP /var/lib/dokku/data/storage/$DAILY_FILES:$RSS_FILE_PATH

VARS="$VARS RSS_FILE_PATH=$RSS_FILE_PATH"
VARS="$VARS SAVE_RSS_FILES=0"

################

if dokku graphite:exists $GRAPHITE_STATS_SVC >/dev/null 1>&2; then
    echo found dokku-graphite $GRAPHITE_STATS_SVC
else
    dokku graphite:create $GRAPHITE_STATS_SVC
    dokku graphite:nginx-expose $GRAPHITE_STATS_SVC stats.$(hostname -s).mediacloud.org
fi

dokku graphite:link $GRAPHITE_STATS_SVC $APP

# should be dokku-graphite-$GRAPHITE_STATS_SVC:
STATSD_HOST=$(dokku graphite:info stats --dsn | sed -e '@statsd://@@' -e 's@:[0-9]*$@@')

STATSD_PREFIX="mc.$(TYPE_OR_UNAME).rss-fetcher"

VARS="$VARS MC_STATSD_HOST=$STATSD_HOST"
VARS="$VARS MC_STATSD_PREFIX=$STATSD_PREFIX"

################
# set config vars
# make all changes to VARS before this!!!

dokku config:set $APP $VARS

################

DOKKU_KEYS=~dokku/.ssh/authorized_keys
if [ "x$PUBKEY_FILE" != x -a -f $DOKKU_KEYS ]; then
    # get user id from .pub file
    XUSER=$(awk '{ print $3; exit 0 }' $PUBKEY_FILE)
    if grep "$XUSER" $DOKKU_KEYS >/dev/null; then
        echo found $XUSER in dokku admin ssh keys
    else
	echo adding $PUBKEY_FILE to dokku admin ssh keys
	# must be a pipe?!
	cat $PUBKEY_FILE | dokku ssh-keys:add $UNAME
    fi
fi

################
# from https://www.freecodecamp.org/news/how-to-build-your-on-heroku-with-dokku/

# XXX need DOMAIN and to set DOKKU_LETSENCRYPT_EMAIL in install-dokku.sh

# This requires $APP.$DOMAIN to be visible from Internet:

# set a custom domain that you own for your application
#dokku domains:set $APP $APP.$DOMAIN

# Enable Let's Encrypt
#dokku letsencrypt:enable $APP

################

echo installing $CRONTAB

test -d $LOGDIR || mkdir -p $LOGDIR
cat >$CRONTAB <<EOF
# runs script specified in Procfile: any args are passed to that script
#*/30 * * * * root /usr/bin/dokku run $APP fetcher >> $LOGDIR/fetcher.log 2>&1
30 0 * * * root /usr/bin/dokku run $APP generator >> $LOGDIR/generator.log 2>&1
EOF

echo installing $LOGROTATE

cat >$LOGROTATE <<EOF
$LOGDIR/*.log {
  rotate 12
  monthly
  compress
  missingok
  notifempty
}
EOF

# for production:
# dokku postgres:backup-auth rss-fetcher-db AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
# dokku postgres:backup-schedule rss-fetcher-db "0 1 * * *" mediacloud-rss-fetcher-backup
#
# creates /etc/cron.d/dokku-postgres-rss-fetcher-db ??
# 0 1 * * * dokku /usr/bin/dokku postgres:backup rss-fetcher-db mediacloud-rss-fetcher-backup 
