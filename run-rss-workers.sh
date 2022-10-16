#!/bin/sh

# now invoked from Procfile.

if [ "x$MC_WORKER_LOG_LEVEL" = x ]; then
    if [ "x$GIT_REV" = x ]; then
	# invoked outside Dokku; use old run-rss-workers.sh default
	MC_WORKER_LOG_LEVEL=debug
    else
	# invoked inside Dokku; use old Procfile default
	MC_WORKER_LOG_LEVEL=info
    fi
fi

# NOTE! each invocation of this script runs ONE worker process,
# so the number of workers is controlled by
# "dokku ps:scale rss-fetcher NUMBER"

python -m scripts.worker -l $MC_WORKER_LOG_LEVEL "$@"

