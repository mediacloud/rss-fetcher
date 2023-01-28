#!/bin/sh

# output a URL suitable for use as (backup-rss-fetcher) DATABASE_URL
# for a Dokku postgres service in the outside world.
# Phil Budne, January 2023

SVC="$1"
if [ "x$SRC" = x ]; then
    echo "Usage: $0 dokku-postgres-service-name" 1>&2
    exit 1
fi

ssh dokku@$(hostname) postgres:info $SVC | awk "
/Dsn:/ { dsn = \$2 }
/Internal ip:/ { ip = \$3
	print gensub(/^postgres:/, \"postgresql:\", 1, 
		gensub(/dokku-postgres-$SVC/, ip, 1, dsn))
	exit 0
}"
