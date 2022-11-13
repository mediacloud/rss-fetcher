#!/bin/sh

# clone production rss-fetcher database
# (and randomize next_fetch_attempt)
# for development/testing.

DB="$1"

PROD=tarbell.angwin

HOST=$(hostname)
PROD_DB=rss-fetcher

SCRIPT_DIR=$(dirname $0)

if [ "x$DB" = x ]; then
    echo "Usage: $0 dokku-pg-service-name" 1>&2
    exit 1
fi

alias prod="ssh dokku@$(hostname)"
if [ $(whoami) = root ]; then
    if [ $HOST = $PROD ]; then
	alias prod=dokku
    fi
    alias local=dokku
else
    alias prod="ssh dokku@$PROD"
    alias local="ssh dokku@$HOST"
fi

echo checking $PROD_DB access
if ! prod postgres:exists $PROD_DB >/dev/null 2>&1; then
    echo "cannot access $PROD $PROD_DB" 1>&2
    exit 2
fi
echo checking if $DB exists
if ! local postgres:exists $DB >/dev/null 2>&1; then
    echo "cannot access $DB" 1>&2
    exit 2
fi

echo starting copy...
prod postgres:export $PROD_DB | local postgres:import $DB

$SCRIPT_DIR/randomize-feeds.sh $DB
