#!/bin/sh

# script to assign random values to feeds.next_fetch_attempt
# run by clone-database.sh
# can also be run when your database hasn't been active

DB="$1"

if [ $(whoami) != root ]; then
    alias dokku="ssh dokku@$(hostname)"
fi

if [ "x$DB" = x ]; then
    echo "Usage: $0 dokku-pg-service-name" 1>&2
    exit 1
fi
if ! dokku postgres:exists $DB >/dev/null 2>&1; then
    echo "Database $DB not found"
    exit 2
fi
echo "randomizing $DB feeds"
echo "update feeds set next_fetch_attempt = NOW() + (random() * '12 hours'::interval);" | dokku postgres:connect $DB
