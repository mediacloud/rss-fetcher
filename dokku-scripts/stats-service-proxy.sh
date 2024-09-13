#!/bin/sh

# Phil Budne, October 2022

# NOTE! this script normally invoked from dokku-scripts/create-stats.sh

# create proxy app for letsencrypt https certificate for a LOCAL
# dokku-graphite service (letsencypt plugin only supports certs for apps).

# If you want a proxy for a stats server on a server which is on a
# server that isn't Internet visible, see dokku-scripts/http-proxy.sh

# from https://github.com/dokku/dokku-graphite/issues/18#issuecomment-917603293
# suggestion by Jose Diaz-Gonzalez (Señor Dokku?)

# name of stats service (should be obscure, since it will be visible at port 80):
SERVICE=$1

# name of proxy app (publicly visible name):
PROXY_APP=$2

if [ "x$SERVICE" = x -o "x$PROXY_APP" = x -o "x$SERVICE" = "x$PROXY_APP" ]; then
    echo Usage: $0 GRAPHITE_SERVICE_NAME PROXY_APP_NAME 1>&2
    exit 1
fi
HOST=$(hostname -s)

SCRIPT_DIR=$(dirname $0)
COMMON_SH=$SCRIPT_DIR/common.sh
INSTANCE=ignored
if [ ! -f $COMMON_SH ]; then
    echo cannot find $COMMON_SH 1>&2
    exit 1
fi
. $COMMON_SH

DOMAIN=$BASTION.$PUBLIC_DOMAIN

if ! public_server; then
    echo must be run on Internet visible server 1>&2
    exit 1
fi

if ! dokku graphite:exists $SERVICE >/dev/null 2>&1; then
    echo dokku-graphite service $SERVICE not found
    exit 1
fi

if dokku apps:exists $PROXY_APP >/dev/null 2>&1; then
    echo Dokku app $PROXY_APP exists
    exit 1
fi

echo creating service-proxy app $PROXY_APP for graphite https access
set -x
dokku apps:create $PROXY_APP
dokku config:set $PROXY_APP SERVICE_NAME=$SERVICE SERVICE_TYPE=graphite SERVICE_PORT=80
dokku graphite:link $SERVICE $PROXY_APP
dokku git:from-image $PROXY_APP dokku/service-proxy:latest
dokku domains:set $PROXY_APP $PROXY_APP.$DOMAIN
# not in global config on tarbell:
dokku config:set $PROXY_APP --no-restart DOKKU_LETSENCRYPT_EMAIL=$DOKKU_LETSENCRYPT_EMAIL
dokku letsencrypt:enable $PROXY_APP
