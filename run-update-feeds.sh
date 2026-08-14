#!/bin/sh

# run via app.json cronjob which gives an argv (not a command line
# interpreted by a shell) so conditionalization and redirection must
# be done here!

# send stdout/err to a log file
# log not rotated, so overwrite each time

# relative, for running outside:
STORAGE=storage
LOG=run-update-feeds.log

OPTIONS=
for ARG in "$@"; do
    case "$ARG" in
    --full-sync)
	OPTIONS="$OPTIONS --full-sync"
	LOG=run-update-feeds-full.log;;
    *) log "bad option $ARG"; exit 1;;
    esac
done

exec > $STORAGE/logs/$LOG 2>&1

log() {
    echo `date '+%F %T'` $*
}

# set by deploy.py:
if [ "x$RSS_FEED_UPDATE_ENABLE" = x ]; then
    log "not enabled"
    exit 0
fi

log start $0
python -m scripts.update_feeds $OPTIONS
# RIGHT after python command!
log "status: $?"
