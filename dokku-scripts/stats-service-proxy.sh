#!/bin/sh

# create proxy app for letsencrypt certificate for dokku-graphite service
# (letsencypt plugin only supports certs for apps)
# Phil Budne, October 2022

# NOT YET TESTED!!!

# from https://github.com/dokku/dokku-graphite/issues/18
# "In this example, a graphite service named $SERVICE will be exposed under the app $PROXY_APP"
# (unknown as yet whether SERVICE == PROXY_APP will work)

SERVICE=$1
PROXY_APP=$2

HOST=$(hostname -s)

SCRIPT_DIR=$(dirname $0)
INSTALL_CONF=$SCRIPT_DIR/install-dokku.conf
if [ ! -f $INSTALL_CONF ]; then
    echo cannot find $INSTALL_CONF 1>&2
    exit 1
fi
. $INSTALL_CONF

DOMAIN=$BASTION.$PUBLIC_DOMAIN

# test for angwin cluster:
if ! public_server; then
    echo must be run on Internet visible server 1>&2
    exit 1
fi

if dokku apps:list | grep -F -x $PROXY_APP >/dev/null; then
    echo Dokku app $PROXY_APP exists
    exit 1
fi

echo creating service-proxy app $PROXY_APP for graphite https access
dokku apps:create $PROXY_APP
dokku config:set $PROXY_APP SERVICE_NAME=$SERVICE SERVICE_TYPE=graphite SERVICE_PORT=80
dokku graphite:link $SERVICE $PROXY_APP
dokku git:from-image $PROXY_APP dokku/service-proxy:latest
dokku domains:set $PROXY_APP $PROXY_APP $PROXY_APP.$DOMAIN
dokku letsencrypt:enable $PROXY_APP
