#!/bin/sh

# sync synthetic RSS files to cloud storage

# Run from app.json, which is:
# * hard wired (runs regardless of prod/staging/dev)
# * directly runs an executable, not a shell command
#	so no test && ... or output redirection possible
# SO: conditionalization/redirection must be done here.

# relative, for running outside:
DATA=data

# send stdout/err to a log file
# log not rotated, so overwrite each time
exec > $DATA/logs/run-cloud-sync-rss.log 2>&1

log() {
    echo `date '+%F %T'` $*
}

# from private config:
if [ "x$RSS_CLOUD_SYNC_ENABLE" = x ]; then
    log "not enabled"
    exit 0
fi

log start $0

# from private config:
if [ "x$RSS_CLOUD_SYNC_ACCESS_KEY" = x -o \
     "x$RSS_CLOUD_SYNC_SECRET_KEY" = x -o \
     "x$RSS_CLOUD_SYNC_BUCKET" = x -o \
     "x$RSS_CLOUD_SYNC_PATH" = x -o ]; then
    log "missing config"
    env
    exit 0
fi

# put keys in environment where awscli looks for them:
export AWS_ACCESS_KEY=$RSS_CLOUD_SYNC_ACCESS_KEY
export AWS_SECRET_KEY=$RSS_CLOUD_SYNC_SECRET_KEY

OPTIONS=
if [ "x$RSS_CLOUD_SYNC_ENDPOINT" != x ]; then
    # always the case for B2: endpoint contains region
    OPTIONS="$OPTIONS --endpoint $RSS_CLOUD_SYNC_ENDPOINT"
elif [ "x$RSS_CLOUD_SYNC_REGION" != x ]; then
    # no endpoint: make sure we have region for awscli
    OPTIONS="$OPTIONS --region $RSS_CLOUD_SYNC_REGION"
fi

# awscli wants "s3" URL regardless of backing store!!
# b2 commands tend to want bucket separately
# continuing to use awscli because it works,
# and b2 command didn't behave as expected
DEST=s3://$RSS_CLOUD_SYNC_BUCKET$RSS_CLOUD_SYNC_PATH

# TEMP:
env

set -x
aws s3 sync $OPTIONS $DATA/rss-output-files/ $DEST
# RIGHT after command!
log "status: $?"
