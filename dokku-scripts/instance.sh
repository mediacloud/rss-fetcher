#!/bin/sh

# create or destroy an rss-fetcher dokku instance
# takes two arguments: action and type
# action: create or destroy
# type: prod, staging, or UNAME
#	(UNAME must be a user in passwd file)

# Phil Budne, September 2022

OP="$1"
INSTANCE="$2"

TMP=/tmp/dokku-instance-$$
trap "rm -f $TMP" 0
touch $TMP
chmod 600 $TMP

case "$OP" in
create|destroy)
    case "$INSTANCE" in
    prod|staging) ;;
    *)
        if ! id $INSTANCE >/dev/null 2>&1; then
            echo "$0: user $INSTANCE does not exist"
            exit 1
        fi
	;;
    esac
    ;;
*) ERR=1;
esac

if [ "x$ERR" != x ]; then
    echo "usage: $0 create|destroy NAME" 1>&2
    echo "    where NAME is 'prod', 'staging' or 'USERNAME'" 1>&2
    exit 1
fi

SCRIPT_DIR=$(dirname $0)
COMMON_SH=$SCRIPT_DIR/common.sh
if [ ! -f $COMMON_SH ]; then
    echo cannot find $COMMON_SH 1>&2
    exit 1
fi
. $COMMON_SH

check_not_root

# Service names:
DATABASE_SVC=$APP
# needed to delete old service:
REDIS_SVC=$APP

# STORAGE mount point inside container
STORAGE_MOUNT_POINT=/app/storage

destroy_service() {
    PLUGIN=$1
    SERVICE=$2
    if dokku $PLUGIN:exists $SERVICE >/dev/null 2>&1; then
	if dokku $PLUGIN:linked $SERVICE $APP; then
	    echo unlinking $PLUGIN service $SERVICE
	    dokku $PLUGIN:unlink $SERVICE $APP
	fi
	echo "destroying $PLUGIN service $SERVICE"
	dokku $PLUGIN:destroy $SERVICE
    fi
}

if [ "x$OP" = xdestroy ]; then
    # XXX make into a destroy function so can be used for teardown in case create fails??
    if ! dokku apps:exists $APP >/dev/null 2>&1; then
	echo app $APP not found 1>&2
	exit 1
    fi

    # destroy commands ask for confirmation: bug or feature??
    # (add --force to suppress??)

    dokku apps:destroy $APP
    destroy_service postgres $DATABASE_SVC
    ## end destroy function

    exit 0
fi

################
# check git remotes first

if git remote | grep "^$DOKKU_GIT_REMOTE\$" >/dev/null; then
    echo found git remote $DOKKU_GIT_REMOTE
else
    echo adding git remote $DOKKU_GIT_REMOTE
    git remote add $DOKKU_GIT_REMOTE dokku@$FQDN:$APP
fi
################

if dokku apps:exists $APP >/dev/null 2>&1; then
    echo found app $APP 1>&2
else
    echo creating app $APP
    if dokku apps:create $APP; then
	echo OK
    else
	STATUS=$?
	echo ERROR: $STATUS
	exit $STATUS
    fi
fi

################
# helper for service creation
# must not be called before app creation

check_service() {
    local PLUGIN=$1
    shift
    local SERVICE=$1
    shift
    local APP=$1
    shift
    local CREATE_OPTIONS="$*"

    if dokku $PLUGIN:exists $SERVICE >/dev/null 2>&1; then
	echo "found $PLUGIN service $SERVICE"
    else
	if [ "x$CREATE_OPTIONS" != x ]; then
	    echo creating $PLUGIN service $SERVICE w/ options $CREATE_OPTIONS
	else
	    echo creating $PLUGIN service $SERVICE
	fi

	dokku $PLUGIN:create $SERVICE $CREATE_OPTIONS
	# XXX check status & call destroy on failure?
    fi

    if dokku $PLUGIN:linked $SERVICE $APP >/dev/null 2>&1; then
	echo "$PLUGIN service $SERVICE already linked to app $APP"
    else
	echo linking $PLUGIN service $SERVICE to app $APP
	dokku $PLUGIN:link $SERVICE $APP
	# XXX check status
    fi
}

################

# no current need for redis:
destroy_service redis $REDIS_SVC

################

# vacuum fails w/ shm-size related error:
# consider passing --shm-size SIZE?
# see https://github.com/dokku/dokku-postgres
check_service postgres $DATABASE_SVC $APP

################
# non-volatile storage

if [ -d $STDIR ]; then
    echo using $STORAGE dir $STDIR
else
    echo creating $STORAGE storage dir $STDIR
    dokku storage:ensure-directory $STORAGE
fi

if dokku storage:list $APP | fgrep "$STDIR:$STORAGE_MOUNT_POINT" >/dev/null; then
    echo storage directory $STDIR linked to app dir $STORAGE_MOUNT_POINT
else
    echo linking storage directory $STDIR to app dir $STORAGE_MOUNT_POINT
    dokku storage:mount $APP $STDIR:$STORAGE_MOUNT_POINT
fi

################
# check for, or create stats service, and link to our app

echo checking for stats service...
$SCRIPT_DIR/create-stats.sh $INSTANCE $APP
echo ''

################ remove old process types

# compare names in Procfile w/ those in $SCALE_FILE??
SCALE_FILE=/var/lib/dokku/config/ps/$APP/scale

remove_process_type() {
    NAME=$1
    if grep "^$NAME=" $SCALE_FILE >/dev/null; then
	echo removing $NAME process type
	sed -i "/^$NAME=/d" $SCALE_FILE
    fi
}
#remove_process_type archiver
#remove_process_type generator
#remove_process_type update
#remove_process_type worker

################
# from https://www.freecodecamp.org/news/how-to-build-your-on-heroku-with-dokku/

if public_server; then
    DOMAINS="$APP.$HOST.$PUBLIC_DOMAIN"
else
    DOMAINS="$APP.$FQDN $APP.$HOST"
fi

# NOTE ensures leading and trailing spaces:
CURR_DOMAINS=$(dokku domains:report $APP | grep '^ *Domains app vhosts:' | sed -e 's/^.*: */ /' -e 's/$/ /')
ADD=""
for DOM in $DOMAINS; do
    if echo "$CURR_DOMAINS" | fgrep " $DOM " >/dev/null; then
	echo " $DOM already configured"
    else
	ADD="$ADD $DOM"
    fi
done
if [ "x$ADD" != x ]; then
    echo "adding domain(s): $ADD"
    dokku domains:add $APP $ADD
fi

if public_server; then
    if ! dokku letsencrypt:active $APP >/dev/null; then
	echo enabling lets encrypt
	# This requires $APP.$HOST.$PUBLIC_DOMAIN to be visible from Internet:
	dokku letsencrypt:enable $APP
    fi
fi

# save script fingerprint of this, so push can check instance up-to-date
# XXX set only if needed?
SCRIPT_HASH=$(instance_sh_file_git_hash)
dokku config:set --no-restart $APP $INSTANCE_HASH_VAR=$SCRIPT_HASH

# XXX is production, run crontab/ssh-key script under sudo?!!!!
