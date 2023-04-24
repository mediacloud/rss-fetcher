#!/bin/sh

# create or destroy an rss-fetcher dokku instance
# takes two arguments: action and type
# action: create or destroy
# type: prod, staging, or dev-UNAME
#	(UNAME must be a user in passwd file)

# Phil Budne, September 2022
# redo using ansible so configuration captured (use ansible vault for
# sensitive params) and make this a wrapper that invokes ansible??

SCRIPT_DIR=$(dirname $0)
INSTALL_CONF=$SCRIPT_DIR/install-dokku.conf
if [ ! -f $INSTALL_CONF ]; then
    echo cannot find $INSTALL_CONF 1>&2
    exit 1
fi
. $INSTALL_CONF

# needs root access for ssh key install to ~dokku
# and install to /etc/cron.d
check_root

OP="$1"
NAME="$2"

HOST=$(hostname -s)
# local access:
FQDN=$(hostname -f)

TYPE="$NAME"
TYPE_OR_UNAME="$TYPE"

TMP=/tmp/dokku-instance-$$
trap "rm -f $TMP" 0
touch $TMP
chmod 600 $TMP

# XXX check that this script is clean (checked in?)

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

# NOTE! used for filename in /etc/cron.d, so must contain only alphanum dots and dashes?
APP=${PREFIX}rss-fetcher

MCWEB_APP=${PREFIX}mcweb

# PLB: this may no longer be needed: UMass has set up DNS in the
# angwin cluster so that *.tarbell.mediacloud.org resolves to the
# private (10.x.x.x) address of tarbell.  This needs to be set up on a
# per-server basis, and setting NET allows inter-app access on a
# single server without special arrangement (*BUT* you still need to
# use plaintext http and the private port, because getting a let's
# encrypt certificate requires having an Internet accessible URL.

# NET is OPTIONAL: if set, confers the ability to resolve docker
# container names (ie; appname.procname.N) to container IP addresses.
# The remote app does NOT need to be on the same docker network (unless they
# also need to be able to resolve container names to IP addresses, as
# is the case for mcweb and rss-fetcher), so the network doesn't
# need to be "realm" (prod/staging/dev) specific.
NET=mcweb

# Service names:
DATABASE_SVC=$(app_to_db_svc $APP)

# non-volatile storage mount for generated RSS files, db CSV files, logs
STORAGE=${APP}-storage
# STORAGE mount point inside container
STORAGE_MOUNT_POINT=/app/storage
# Location of storage dir from outside container:
STDIR=$STORAGE_HOME/$STORAGE

# filename must use letters and dashes only!!!:
CRONTAB=/etc/cron.d/$APP

# server log directory for crontab entries.
# files not rotated, so only save output from last invocation.
LOGDIR=/var/tmp

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
    destroy_service redis $REDIS_SVC
    destroy_service postgres $DATABASE_SVC

    rm -f $CRONTAB dokku-postgres-$APP
    ## end destroy function

    exit 0
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
# check git remotes first

# name of git remote for this dokku app:
REM=dokku_$TYPE_OR_UNAME

if git remote | grep "^$REM\$" >/dev/null; then
    echo found git remote $REM
else
    echo adding git remote $REM
    GIT_OWNER=$(stat -c %U .git)
    su $GIT_OWNER -c "git remote add $REM dokku@$HOST:$APP"
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
# helper to get internal web server port for an app

app_http_port() {
    APP=$1
    # example DOKKU_PROXY_PORT_MAP value: http:80:5000 https:443:5000
    dokku config:get $APP DOKKU_PROXY_PORT_MAP | awk '{ print $NF }' | awk -F: '{ print $3 }'
}

app_http_url() {
    APP=$1
    # return docker DNS name and port for APP's web server
    # NOTE! mcweb.web wired into mcweb/settings.py ALLOWED_HOSTS list
    echo "http://$APP.web:$(app_http_port $APP)"
}

if [ "x$NET" != x ]; then
    if dokku network:exists $NET >/dev/null; then
	echo network $NET exists
    else
	echo creating network $NET
	dokku network:create $NET
    fi

    # see comments on NET= line above.
    # mcweb app network set at end.
    if [ "x$(dokku network:report $APP --network-attach-post-create)" = "x$NET" ]; then
	echo app attach-post-create network already set
    else
	echo setting app attach-post-create network
	dokku network:set $APP attach-post-create $NET
    fi

    if dokku apps:exists $MCWEB_APP >/dev/null 2>&1; then
	echo found $MCWEB_APP app

	# get the http port for mcweb listener
	MCWEB_URL=$(app_http_url $MCWEB_APP)
	echo MCWEB_URL=$MCWEB_URL
	add_vars MCWEB_URL=$MCWEB_URL
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
$SCRIPT_DIR/create-stats.sh $APP
echo ''

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
remove_process_type archiver
remove_process_type generator
remove_process_type update
remove_process_type worker

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
    # Enable Let's Encrypt
    # This requires $APP.$HOST.$PUBLIC_DOMAIN to be visible from Internet:
    dokku letsencrypt:enable $APP
fi
################ crontab

if [ "x$LOGDIR" != x/var/tmp ]; then
    # NOTE!!! LOGDIR for crontabs outside of app "storage" area; only saving output of last run
    # all scripts/*.py log to /app/storage/logs, w/ daily rotation and 7 day retention
    test -d $LOGDIR || mkdir -p $LOGDIR
fi

CRONTEMP="/tmp/$APP.cron.tmp"

# prevent world/group write to CRONTEMP/CRONTAB
umask 022

# run periodic scripts in fetcher container rather than firing up a
# new container just for the duration of the script.
DOKKU_RUN_PERIODIC="/usr/bin/dokku enter $APP fetcher"

cat >$CRONTEMP <<EOF
# MACHINE CREATED!!! PLEASE DO NOT EDIT THIS FILE!!!
# edit and run rss-fetcher/dokku-scripts/instance.sh instead!!!!!!
#
#
# only saving output from last run; all scripts log to /app/storage/logs now
$PERIODIC
# generate RSS output files (try multiple times a day, in case of bad code, or downtime)
# NOTE! production instance runs "aws s3 sync" hourly lower down in crontab, and shouldn't
# run too soon after to allow generator to run to completion.
15 * * * * root $DOKKU_RUN_PERIODIC ./run-gen-daily-story-rss.sh > $LOGDIR/$APP-generator.log 2>&1
#
# archive old DB table entries (non-critical); production aws s3 sync should run after this
# (before 2am standard time rollback, in case we never get rid of time changes, and server not configured in UTC)
30 1 * * * root $DOKKU_RUN_PERIODIC python -m scripts.db_archive --verbose --delete > $LOGDIR/$APP-archiver.log 2>&1
EOF

# maybe do backups for staging as well (to fully test this script)?!
# would need separate buckets (and keys for those buckets),
# or at least a different prefix in the same bucket).

DB_BACKUP_POLICY=mediacloud-web-tools-db-backup-get-put-delete
DB_BACKUP_KEYNAME=mediacloud-webtools-db-backup

if [ "x$TYPE" = xprod ]; then
    if dpkg --list | grep awscli >/dev/null; then
	echo found awscli
    else
	echo installing awscli
	apt install -y awscli
    fi

    # use to run aws s3 sync for RSS files and DB backup
    # only requires that user be permenant, and have read access to $STDIR
    BACKUP_USER=root
    AWS_CREDS_DIR=$(eval echo ~$BACKUP_USER)/.aws
    AWS_CREDS=$AWS_CREDS_DIR/credentials

    # profiles (section) in $AWS_CREDS file
    DB_BACKUP_PROFILE=${APP}-backup
    RSS_PROFILE=${APP}-rss

    DB_BACKUP_BUCKET=mediacloud-rss-fetcher-backup
    RSS_BUCKET=mediacloud-public/backup-daily-rss

    BOGUS_DB_BACKUP_CRED="${DB_BACKUP_PROFILE}-key-here"
    BOGUS_RSS_CRED="${RSS_PROFILE}-key-here"

    test -d $AWS_CREDS_DIR || mkdir $AWS_CREDS_DIR
    check_aws_creds() {
	local PROFILE=$1
	local BOGUS=${PROFILE}-replace-me
	local POLICY=$2
	local KEYNAME=$3
	if ! grep "\[$PROFILE\]" $AWS_CREDS >/dev/null 2>&1; then
	    (
		echo "[$PROFILE]"
		echo "aws_access_key_id = $BOGUS"
		echo "aws_secret_access_key = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
	    ) >> $AWS_CREDS
	fi
	if grep $BOGUS $AWS_CREDS >/dev/null; then
	    echo '' 1>&2
	    echo "*** Need valid $PROFILE profile/section in $AWS_CREDS ***" 1>&2
	    echo " (requires key with $POLICY policy attached (ie; $KEYNAME key)" 1>&2
	fi
    }

    check_aws_creds $DB_BACKUP_PROFILE $DB_BACKUP_POLICY $DB_BACKUP_KEYNAME
    check_aws_creds $RSS_PROFILE mediacloud-public-get-put-delete mediawords-public-s3
    chmod 600 $AWS_CREDS
    chown $BACKUP_USER $AWS_CREDS

    # copy generated RSS files to public S3 bucket
    echo "45 * * * * $BACKUP_USER aws s3 --profile $RSS_PROFILE sync $STDIR/rss-output-files/ s3://$RSS_BUCKET/ > $LOGDIR/rss-fetcher-aws-sync-rss-mc.log 2>&1" >> $CRONTEMP

    # copy archived rows in CSV files to private bucket (NOTE! After "run archiver" entry created above)
    echo "45 1 * * * $BACKUP_USER aws s3 --profile $DB_BACKUP_PROFILE sync $STDIR/db-archive/ s3://$DB_BACKUP_BUCKET/ > $LOGDIR/rss-fetcher-aws-sync-dbarch-mc.log 2>&1" >> $CRONTEMP

    # sync feeds from mcweb (web-search server)
    echo "*/5 * * * * root $DOKKU_RUN_PERIODIC python -m scripts.update_feeds > $LOGDIR/rss-fetcher-update.log 2>&1" >> $CRONTEMP
fi

if [ -f $CRONTAB ]; then
    if cmp -s $CRONTAB $CRONTEMP; then
	echo no change to $CRONTAB
	rm -f $CRONTEMP
    else
	SAVE=/tmp/$APP.cron.$$
	echo $CRONTAB differs, saving as $SAVE
	mv $CRONTAB $SAVE
	echo installing new $CRONTAB
	mv $CRONTEMP $CRONTAB
    fi
else
    echo installing $CRONTAB
    mv $CRONTEMP $CRONTAB
fi

if [ "x$TYPE" = xprod ]; then
    DB_BACKUP_DIR=/var/lib/dokku/services/postgres/$DATABASE_SVC/backup

    # backup-auth creates $DB_BACKUP_DIR/AWS{,_SECRET}_ACCESS_KEY files
    if [ -f $DB_BACKUP_DIR/AWS_ACCESS_KEY_ID -a \
	    -f $DB_BACKUP_DIR/AWS_SECRET_ACCESS_KEY ]; then
	echo found AWS keys for postgres:backup
    else
	# ansible could get keys from an encrypted "vault" file
	echo '' 1>&2
	echo '*** AWS keys for postgres:backup not found!!!' 1>&2
	echo "run: dokku postgres:backup-auth $DATABASE_SVC AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY" 1>&2
	echo ' (where AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY have' 1>&2
	echo " $DB_BACKUP_POLICY (ie; $DB_BACKUP_KEY)" 1>&2
    fi

    # backup-schedule creates creates /etc/cron.d/dokku-postgres-$DATABASE_SVC w/
    # 0 1 * * * dokku /usr/bin/dokku postgres:backup $DATABASE_SVC $DB_BACKUP_BUCKET
    if [ -f /etc/cron.d/dokku-postgres-$DATABASE_SVC ]; then
	echo found /etc/cron.d/dokku-postgres-$DATABASE_SVC
    else
	echo scheduling backup of $DATABASE_SVC service to s3 bucket $DB_BACKUP_BUCKET
	dokku postgres:backup-schedule $DATABASE_SVC "0 1 * * *" $DB_BACKUP_BUCKET
    fi
fi

# configure mcweb app
if dokku apps:exists $MCWEB_APP >/dev/null 2>&1; then
    echo found $MCWEB_APP app
    if [ "x$NET" != x ]; then
	echo network $NET
        if [ "x$(dokku network:report $MCWEB_APP --network-attach-post-create)" = "x$NET" ]; then
	    echo $MCWEB_APP attach-post-create network already set
	else
	    echo setting $MCWEB_APP attach-post-create network
	    dokku network:set $MCWEB_APP attach-post-create $NET
	    MCWEB_RESTART=1
	fi

	# get the http port for our OpenAPI listener inside web container
	# (requires that rss-fetcher be deployed)
	RSS_FETCHER_URL=$(app_http_url $APP)

	if [ "x$(dokku config:get $MCWEB_APP RSS_FETCHER_URL)" = "x$RSS_FETCHER_URL" ]; then
	    echo $MCWEB_APP RSS_FETCHER_URL already set
	    if [ "x$MCWEB_RESTART" != x ]; then
		# no config change, but need restart.
		# only one process, so no need to get picky
		echo restarting $MCWEB_APP app
		dokku ps:restart $MCWEB_APP
	    fi
	else
	    # will restart app
	    echo setting $MCWEB_APP app RSS_FETCHER_URL config to $RSS_FETCHER_URL
	    dokku config:set $MCWEB_APP RSS_FETCHER_URL=$RSS_FETCHER_URL
	fi
    fi
fi

# save script fingerprint of this, so push can check instance up-to-date
# XXX should check that script checked in at top!
SCRIPT_HASH=$(git_hash $0)
dokku config:set --no-restart $APP INSTANCE_SH_GIT_HASH=$SCRIPT_HASH
