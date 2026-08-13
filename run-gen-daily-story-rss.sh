#!/bin/sh

# run from app.json cron entry hourly
# (if only run once a day is vulnerable to missing due
# to downtime, reboot etc)

# relative, for running outside:
STORAGE=storage

# send stdout/err to a log file
# log not rotated, so overwrite each time
exec > $STORAGE/logs/run-gen-daily-story-rss.log 2>&1

log() {
    echo `date '+%F %T'` $*
}

log start
python -m scripts.gen_daily_story_rss --quiet "$@"
# directly after python command
log "status: $?"
