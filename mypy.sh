#!/bin/sh
# emacs: -*- compile-command: "./mypy.sh" -*-

# Script phil uses to run mypy; see also mypy.ini

# a work in progress; still generates some noise
# some causes may be:
# * mcmetadata lacks py.typed?
# * available stubs for sqlalchemy are out of date??
#	missing: Session.begin(), PendingRollbackError
# * no type hints for: feedparser, rq, statsd, uvicorn
#	(could put our own .pyi files in stubs/)

# Phil runs this under emacs by opening this file, then:
# M-x compile<RET>
# <RET>
# then stepping through the messages with c-x ` (next-error)
# to re-run, go back to the mypy.sh buffer and repeat.

# expected to be run in a venv w/ requirements.txt installed
VENV=venv
if [ ! -d $VENV ]; then
    echo creating venv
    python -mvenv $VENV
fi
. ./$VENV/bin/activate

# XXX check if requirements.txt newer than .turd?
if [ ! -f $VENV/.requirements ]; then
    echo installint requirements
    pip install -r requirements.txt
    touch $VENV/.requirements
fi

# install mypy etc. in venv
# XXX check if mypy-requirements.txt newer than .turd?
if [ ! -f $VENV/.mypy-requirements ]; then
    echo mypy-requirements
    pip install -r mypy-requirements.txt
    touch $VENV/.mypy-requirements
fi

if [ ! -f $VENV/.mypy--install-types ]; then
    echo mypy --install types
    mypy --install-types --non-interactive
    touch $VENV/.mypy--install-types
fi

mypy \
	-mscripts.gen_daily_story_rss \
	-mscripts.import_feeds \
	-mscripts.queue_feeds \
	-mscripts.worker \
	-mserver
