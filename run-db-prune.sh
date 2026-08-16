#!/bin/sh

# relative, for running outside:
DATA=data

# send stdout/err to a log file
# log not rotated, so overwrite each time
exec > $DATA/logs/run-db-prune.log 2>&1

log() {
    echo `date '+%F %T'` $*
}

log start $0
python -m scripts.db_archive --verbose --delete
# directly after python command
log "status: $?"
