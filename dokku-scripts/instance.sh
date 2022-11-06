#!/bin/sh

# create or destroy an rss-fetcher dokku instance
# takes two arguments: action and type
# action: create or destroy
# type: prod, staging, or dev-UNAME
#	(UNAME must be a user in passwd file)

# Phil Budne, September 2022
# redo using ansible (make idempotent, run on every push)
# so configuration captured (use ansible vault for sensitive params)??
# make this a wrapper that invokes ansible??

SCRIPT_DIR=$(dirname $0)
INSTALL_CONF=$SCRIPT_DIR/install-dokku.conf
if [ ! -f $INSTALL_CONF ]; then
    echo cannot find $INSTALL_CONF 1>&2
    exit 1
fi
. $INSTALL_CONF

check_root

OP="$1"
NAME="$2"

HOST=$(hostname -s)
# local access:
FQDN=$(hostname -f)

TYPE="$NAME"
TYPE_OR_UNAME="$TYPE"
case "$OP" in
create|destroy)
    case "$NAME" in
    prod) PREFIX='';;
    staging) PREFIX='staging-';;
    dev-*) UNAME=$(echo "$NAME" | sed 's/^dev-//')
	   case "$UNAME" in
	   prod|staging) echo "bad dev name $UNAME" 1>&2; exit 1;;
	   esac
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
# old storage directory name
OLD_STORAGE=${APP}-daily-files
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

################
# create functions

check_service() {
    local PLUGIN=$1
    local SERVICE=$2
    local APP=$3

    if dokku $PLUGIN:exists $SERVICE >/dev/null 2>&1; then
	echo "found $PLUGIN service $SERVICE"
    else
	echo creating $PLUGIN service $SERVICE
	dokku $PLUGIN:create $SERVICE
	# XXX check status & call destroy on failure?
    fi

    if dokku $PLUGIN:linked $SERVICE $APP >/dev/null 2>&1; then
	echo "$PLUGIN service $REDIS_SVC already linked"
    else
	echo linking $PLUGIN service $REDIS_SVC to app $APP
	dokku $PLUGIN:link $REDIS_SVC $APP
	# XXX check status
    fi
}

add_vars() {
    VARS="$VARS $*"
}

################
# before taking any actions:

if public_server; then
    # not in global config on tarbell:
    add_vars DOKKU_LETSENCRYPT_EMAIL=$DOKKU_LETSENCRYPT_EMAIL
fi

# used in fetcher/__init__.py to set APP
# ('cause I didn't see it available any other way -phil)
add_vars MC_APP=$APP

case "$TYPE" in
prod|staging)
    # XXX maybe use .$TYPE (.staging vs .prod)???
    VARS_FILE=.prod
    if grep ^SENTRY_DSN $VARS_FILE >/dev/null; then
	add_vars $(cat $VARS_FILE)
    else
	echo "Need $VARS_FILE file w/ SENTRY_DSN" 1>&2
	exit 1
    fi
    ;;
esac

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
# check git remotes first

# name of git remote for this dokku app:
REM=dokku_$TYPE_OR_UNAME

if git remote | grep "^$REM\$" >/dev/null; then
    echo "found git remote $REM" 1>&2
else
    echo adding git remote $REM
    # XXX maybe use FQDN?
    # XXX maybe auto-fetch (-f flag)
    git remote add $REM dokku@$HOST:$APP
fi

################

if dokku apps:exists $APP >/dev/null 2>&1; then
    echo found app $APP 1>&2
else
    echo echo creating app $APP
    if dokku apps:create $APP; then
	echo OK
    else
	STATUS=$?
	echo ERROR: $STATUS
	exit $STATUS
    fi
fi

################

check_service redis $REDIS_SVC $APP

# parsing automagic REDIS_URL for rq in fetcher/queue.py

################

# display/log in UTC:
add_vars TZ=UTC

add_vars MAX_FEEDS=15000

################

check_service postgres $REDIS_SVC $APP

# postgres: URLs deprecated in SQLAlchemy 1.4
DATABASE_URL=$(dokku postgres:info $DATABASE_SVC --dsn | sed 's@^postgres:@postgresql:@')
add_vars DATABASE_URL=$DATABASE_URL

################
# non-volatile storage

# XXX handle old (rss-fetcher-daily-files) and rename

if [ ! -d $STORAGE_HOME/$STORAGE ]; then
    echo creating $STORAGE storage dir
    dokku storage:ensure-directory $STORAGE
fi

STDIR=$STORAGE_HOME/$STORAGE
OLDSTDIR=$STORAGE_HOME/$OLD_STORAGE

TMP=/tmp/dokku-instance-$$
trap "rm -f $TMP" 0
dokku storage:list pbudne-rss-fetcher > $TMP

if [ -d $OLDSTDIR ]; then
    echo "moving storage files to new directory"

    OWNER=$(ls -lgd $STDIR | awk '{ print $3 ":" $4 }')
    RSS_DIR=$STDIR/$RSS_OUTPUT_DIR
    if [ ! -d $RSS_DIR ]; then
	mkdir $RSS_DIR
	chown $OWNER $RSS_DIR
    fi
    # XXX check if files exist
    echo moving rss files
    mv $OLDSTDIR/mc*gz $RSS_DIR
    # XXX check for remaining files!
    echo removing $OLDSTDIR
    rmdir $OLDSTDIR
fi

if grep "$OLDSTDIR:$STORAGE_MOUNT_POINT" $TMP >/dev/null; then
    echo removing old storage directory mount
    dokku storage:unmount $APP $OLDSTDIR:$STORAGE_MOUNT_POINT
fi
if grep "$STDIR:$STORAGE_MOUNT_POINT" $TMP >/dev/null; then
    echo found link to storage directory $STDIR to app $STORAGE_MOUNT_POINT
else
    dokku storage:mount $APP $STDIR:$STORAGE_MOUNT_POINT
fi

################
# worker related vars

add_vars SAVE_RSS_FILES=0

# OBSOLETE:
add_vars RSS_FILE_PATH=$STORAGE_MOUNT_POINT

################

# check for, or create stats service, and link to our app
$SCRIPT_DIR/create-stats.sh $APP

# using automagic STATSD_URL in fetcher/stats.py

STATSD_PREFIX="mc.${TYPE_OR_UNAME}.rss-fetcher"
add_vars STATSD_PREFIX=$STATSD_PREFIX

################
# set config vars
# make all add_vars calls before this!!!

# config:set causes redeployment, so check first
touch $TMP
chmod 600 $TMP
dokku config:show $APP | tail -n +2 | sed 's/: */=/' > $TMP
NEED=""
for V in $VARS; do
    # VE var equals
    VE=$(echo $V | sed 's/=.*$/=/')
    # find current value
    CURR=$(fgrep $VE $TMP)
    if [ "x$V" != "x$CURR" ]; then
	NEED="$NEED $V"
    fi
done

if [ "x$NEED" != x ]; then
    echo need to set config: $NEED
    dokku config:set $APP $NEED
fi

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

if public_server; then
    DOMAINS="$APP.$HOST.$BASTION_DOMAIN"
fi
DOMAINS="$DOMAINS $APP.$FQDN $APP.$HOST"

# NOTE leading and trailing spaces:
CURR_DOMAINS=$(dokku domains:report $APP | grep '^ *Domains app vhosts:' | sed -e 's/^.*: */ /' -e 's/$/ /')
ADD=""
for DOM in $DOMAINS; do
    if echo "$CURR_DOMAINS" | fgrep " $DOM " >/dev/null; then
	echo found domain $DOM
    else
	ADD="$ADD $DOM"
    fi
done
if [ "x$ADD" != x ]; then
    echo "adding domain(s): $ADD"
    dokku domains:add $APP $ADD
fi

if public_server; then
    # Enable Let's Encrypt
    # This requires $APP.$HOST.$BASTION_DOMAIN to be visible from Internet:
    dokku letsencrypt:enable $APP
fi
################

CRONTEMP="/tmp/$APP.cron.tmp"

# NOTE!!! LOGDIR outside of app "storage" area; only saving output of last run
# all scripts log to /app/storage/logs, w/ daily rotation and 7 day retention
test -d $LOGDIR || mkdir -p $LOGDIR

if grep '^fetcher:.*--loop' Procfile >/dev/null; then
    PERIODIC="# running fetcher w/ --loop in Procfile: no crontab entry needed"
else
    PERIODIC="*/30 * * * * root /usr/bin/dokku run $APP fetcher > $LOGDIR/fetcher.log 2>&1"
fi

cat >$CRONTEMP <<EOF
# runs script specified in Procfile: any args are passed to that script
# only saving output from last run; all scripts log to /app/storage/logs now
$PERIODIC
# generate RSS output files (try multiple times a day, in case of bad code, or downtime)
30 */6 * * * root /usr/bin/dokku run $APP generator > $LOGDIR/generator.log 2>&1
# archive old DB table entries (non-critical)
45 3 * * * root /usr/bin/dokku run $APP archiver --verbose --delete > $LOGDIR/archiver.log 2>&1
EOF

echo installing $CRONTAB
mv $CRONTEMP $CRONTAB

if [ "x$TYPE" = xprod ]; then
cat <<EOF
MANUALLY:

dokku postgres:backup-auth rss-fetcher-db AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
dokku postgres:backup-schedule rss-fetcher-db "0 1 * * *" mediacloud-rss-fetcher-backup
# creates /etc/cron.d/dokku-postgres-rss-fetcher-db ??
# 0 1 * * * dokku /usr/bin/dokku postgres:backup rss-fetcher-db mediacloud-rss-fetcher-backup 
EOF
fi
