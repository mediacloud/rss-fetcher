#!/bin/sh

# "staging-", for example:
PREFIX="$1"

WEBDB="${PREFIX}mcweb-db"
FETCHER_STORAGE=/var/lib/dokku/data/storage/${PREFIX}rss-fetcher-storage

# %s.%N for "epoch time"?
alias now="date -u '+%FT%T.%N+00'"

if [ $(whoami) != root ]; then
    echo 'sigh; needs to be run as root (unless /app/storage/tmp dir created)'
    exit 1
    #alias dokku="ssh dokku@$(hostname)"
fi

# XXX would not need file if rss-fetcher database saved
# mcweb-db modified_at field (as mcweb_modified_at?):
# we could do "SELECT MAX(mcweb_modified_at) FROM feeds;"

LAST_SYNC_FILE="/var/tmp/${PREFIX}last-sync-feeds"
if [ ! -f "$LAST_SYNC_FILE" ]; then
    now > $LAST_SYNC_FILE
    echo created $LAST_SYNC_FILE file 1>&2
    exit 0
fi

LAST_SYNC="$(cat $LAST_SYNC_FILE)"
THIS_SYNC="$(now)"

echo fetching updates since $LAST_SYNC 1>&2
TMP=/var/tmp/sync-feeds-$$
trap "rm -f $TMP" 0

cat <<EOF | dokku postgres:connect $WEBDB > $TMP
COPY (SELECT *
      FROM sources_feed
      WHERE modified_at >= '$LAST_SYNC' AND modified_at < '$THIS_SYNC'
) TO STDOUT csv header;
EOF

case $(wc -l $TMP) in
0)
    echo "$0: no header CSV header; query failed?" 1>&2
    exit 1
    ;;
1)
    echo "$0: no changes" 1>&2
    exit 0
esac

FILE=updates.csv
STFILE=$FETCHER_STORAGE/$FILE
mv -f $TMP $FETCHER_STORAGE/$FILE
if dokku run $FETCHER_APP run python -m scripts.update_feeds.py /storage/$FILE; then
    echo $THIS_SYNC > $LAST_SYNC_FILE
    STATUS=0
else
    STATUS=$?
    echo "$0: update failed: $STATUS" 1>&2
fi
rm -f $STFILE
exit $STATUS
