#!/bin/sh
# emacs: -*- compile-command: "./mypy.sh" -*-

# Script phil uses to run mypy on Ubuntu 20.04 in a venv
# see also mypy.ini
# NOTE! psycopg2 install requires postgres client library libpq-dev

# * no type hints for feedparser: (could put our own .pyi files in stubs/)
#       errors suppressed via mypy.ini and "# type: ignore[...]"

# Phil runs this file by opening this file in emacs, then:
# M-x compile<RET>
# <RET>
# then stepping through the messages with c-x ` (next-error)
# to re-run, go back to the mypy.sh buffer and repeat.

# allow alternate python interpreter if multiple versions installed:
PYTHON=${PYTHON:-python3}

# expected to be run in a venv w/ requirements.txt installed
VENV=venv2
CACHE='--cache-dir .mypy_cache_alchemy2'

echo using $VENV -- go back to venv when merged!!!
if [ ! -d $VENV ]; then
    echo creating $VENV
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

# seems to work for rq 1.11.1, mcmetadata 0.7.9, uvicorn 0.18.3
for PKG in $VENV/lib/python*/site-packages/rq \
	   $VENV/lib/python*/site-packages/mcmetadata \
	   $VENV/lib/python*/site-packages/uvicorn; do
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

ARGS="$CACHE"
for X in scripts/[a-z]*.py; do
    ARGS="$ARGS -m$(echo $X | sed -e 's@/@.@' -e 's/\.py$//')"
done
echo running mypy $ARGS
mypy $ARGS
