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

PYTHON=${PYTHON:-python3}

# expected to be run in a venv w/ requirements.txt installed
VENV=venv
if [ ! -d $VENV ]; then
    echo creating venv
    $PYTHON -mvenv $VENV || exit 1
fi
. ./$VENV/bin/activate

# from here down "python" symlink available from venv

# XXX check if requirements.txt newer than .turd?
if [ ! -f $VENV/.requirements ]; then
    echo installing requirements
    python -mpip install -r requirements.txt || exit 1
    touch $VENV/.requirements
fi

# install mypy etc. in venv
# XXX check if mypy-requirements.txt newer than .turd?
if [ ! -f $VENV/.mypy-requirements ]; then
    echo installing mypy-requirements
    python -mpip install -r mypy-requirements.txt || exit 1
    touch $VENV/.mypy-requirements
fi

# seems to work for rq 1.11.1
for PKG in $VENV/lib/python*/site-packages/rq  $VENV/lib/python*/site-packages/mcmetadata; do
    if [ -d $PKG -a ! -f $PKG/py.typed ]; then
	echo creating $PKG/py.typed
	touch $PKG/py.typed
    fi
done

# uses cache from a previous run:
#if [ ! -f $VENV/.mypy--install-types ]; then
#    echo mypy --install types
#    mypy --install-types --non-interactive || exit 1
#    touch $VENV/.mypy--install-types
#fi

mypy \
	-mscripts.gen_daily_story_rss \
	-mscripts.import_feeds \
	-mscripts.queue_feeds \
	-mscripts.worker \
	-mserver
