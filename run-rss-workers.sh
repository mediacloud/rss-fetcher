#!/bin/sh

# now invoked from Procfile

if [ "x$MC_WORKER_LOG_LEVEL" = x ]; then
    if [ "x$GIT_REV" = x ]; then
	# invoked outside Dokku; use old run-rss-workers.sh default
	MC_WORKER_LOG_LEVEL=debug
    else
	# invoked inside Dokku; use old Procfile default
	MC_WORKER_LOG_LEVEL=info
    fi
fi

if [ "x$MC_WORKER_CONCURRENCY" = x ]; then
    # must be below DB_POOL_SIZE
    # (XXX check? use MC_WORKER_CONCURRENCY to determine pool size??)
    MC_WORKER_CONCURRENCY=16
fi

# XXX celery args!!!
python -m scripts.worker -A fetcher worker \
       -l $MC_WORKER_LOG_LEVEL \
       --concurrency=$MC_WORKER_CONCURRENCY
