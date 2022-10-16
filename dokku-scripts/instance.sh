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

DOMAIN=$(hostname -s).mediacloud.org

# public facing server (reachable from Internet on port 443)
# enables letsencrypt certs for app (and proxy app for stats service)
if [ "x$DOMAIN" = tarbell.mediacloud.org ]; then
    PUBLIC=1
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
else
    echo will read $SCRIPT_DIR/local-dokku.conf if created
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
# dokku.{postgres,redis}.APP
REDIS_SVC=$APP
DATABASE_SVC=$APP

# storage for generated RSS files
STORAGE=${APP}-storage
# STORAGE mount point inside container:
STORAGE_MOUNT_POINT=/app/storage

# server log directory for scripts run via "dokku run"
LOGDIR=/var/log/dokku/apps/$APP
LOGROTATE=/etc/logrotate.d/$APP
# filename must use letters and dashes only!!!:
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
# before taking any actions:

if [ "x$PUBLIC" != x ]; then
    VARS="$VARS DOKKU_LETSENCRYPT_EMAIL=system@mediacloud.org"
fi

# used in fetcher/__init__.py to set APP
# ('cause I didn't see it available any other way -phil)
VARS="$VARS MC_APP=$APP"

case "$TYPE" in
prod|staging)
    # XXX maybe use .$TYPE (.staging vs .prod)???
    VARS_FILE=.prod
    if grep ^SENTRY_DSN $VARS_FILE >/dev/null; then
	VARS="$VARS $(cat $VARS_FILE)"
    else
	echo "Need $VARS_FILE file w/ SENTRY_DSN" 1>&2
	exit 1
    fi
fi

################ ssh key management

if [ "x$UNAME" = x ]; then
    # production & staging: use logged-in user's key
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

# parsing automagic REDIS_URL for rq in fetcher/queue.py

################

if [ "x$TYPE" = xuser ]; then
    MAX_FEEDS=10
else
    MAX_FEEDS=15000
fi

VARS="$VARS MAX_FEEDS=$MAX_FEEDS"

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
# non-volatile storage

dokku storage:ensure-directory $STORAGE
dokku storage:mount $APP /var/lib/dokku/data/storage/$STORAGE:$STORAGE_MOUNT_POINT

################
# worker related vars

# XXX put rss files in $STORAGE_MOUNT_POINT/rss ???
VARS="$VARS RSS_FILE_PATH=$STORAGE_MOUNT_POINT"
VARS="$VARS SAVE_RSS_FILES=0"

################
# dokku-graphite stats service (can be shared by multiple apps & app instances)

if dokku graphite:exists $GRAPHITE_STATS_SVC >/dev/null 1>&2; then
    echo found dokku-graphite $GRAPHITE_STATS_SVC
else
    dokku graphite:create $GRAPHITE_STATS_SVC

    if [ "x$PUBLIC" != x ]; then
	# proxy app for letsencrypt
	# from https://github.com/dokku/dokku-graphite/issues/18
	# "In this example, a graphite service named $GRAPHITE_STATS_SVC will be exposed under the app $STATS_PROXY"
	# (unknown as yet whether GRAPHITE_STATS_SVC == STATS_PROXY_APP will work)
	STATS_PROXY_APP=stats
	echo creating service-proxy app $STATS_PROXY_APP for graphite https access
	dokku apps:create $STATS_PROXY_APP
	dokku config:set $STATS_PROXY_APP SERVICE_NAME=$GRAPHITE_STATS_SVC SERVICE_TYPE=graphite SERVICE_PORT=80
	dokku graphite:link $GRAPHITE_STATS_SVC $STATS_PROXY_APP
	dokku git:from-image $STATS_PROXY_APP dokku/service-proxy:latest
	dokku domains:set $STATS_PROXY_APP $STATS_PROXY_APP $STATS_PROXY_APP.$DOMAIN
	dokku letsencrypt:enable $STATS_PROXY_APP
    else
	# use unencrypted service on non-public server (via SSH tunnels)
	dokku graphite:nginx-expose $GRAPHITE_STATS_SVC $GRAPHITE_STATS_SVC.$DOMAIN
    fi
fi

dokku graphite:link $GRAPHITE_STATS_SVC $APP

# using automagic STATSD_URL in fetcher/stats.py

STATSD_PREFIX="mc.${TYPE_OR_UNAME}.rss-fetcher"
VARS="$VARS MC_STATSD_PREFIX=$STATSD_PREFIX"

################
if [ "x$PUBLIC" != x ]; then
    # Enable Let's Encrypt
    dokku letsencrypt:enable $APP
fi

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

# set a custom domain that you own for your application
dokku domains:set $APP $APP.$DOMAIN

if [ "x$PUBLIC" != x ]; then
    # Enable Let's Encrypt
    # This requires $APP.$DOMAIN to be visible from Internet:
    dokku letsencrypt:enable $APP
fi

################

echo installing $CRONTAB

test -d $LOGDIR || mkdir -p $LOGDIR

if grep '^fetcher:.*--loop' Procfile >/dev/null; then
    PERIODIC="# running fetcher w/ --loop in Procfile: no crontab entry needed"
else
    PERIODIC="*/30 * * * * root /usr/bin/dokku run $APP fetcher >> $LOGDIR/fetcher.log 2>&1"
fi

cat >$CRONTAB <<EOF
# runs script specified in Procfile: any args are passed to that script
$PERIODIC
# generate RSS output files:
30 0 * * * root /usr/bin/dokku run $APP generator >> $LOGDIR/generator.log 2>&1
EOF

cat >$LOGROTATE <<EOF
$LOGDIR/*.log {
  rotate 12
  monthly
  compress
  missingok
  notifempty
}
EOF

if [ "x$TYPE" = xprod ]; then
cat <<EOF
dokku postgres:backup-auth rss-fetcher-db AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
dokku postgres:backup-schedule rss-fetcher-db "0 1 * * *" mediacloud-rss-fetcher-backup
# creates /etc/cron.d/dokku-postgres-rss-fetcher-db ??
# 0 1 * * * dokku /usr/bin/dokku postgres:backup rss-fetcher-db mediacloud-rss-fetcher-backup 
EOF
fi
