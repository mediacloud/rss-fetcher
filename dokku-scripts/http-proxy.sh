#!/bin/sh

# create a virtual domain with https on a dokku server that is Internet visible
# (ie; tarbell)
# proxying to a plain text HTTP server that's NOT Internet visible.
# (ie; a Dokku app or other web server running on a server on a private net)

# Phil Budne, October 2022
# from https://dokku.com/blog/2021/dokku-0.25.0/
# I use this to expose the grafana interface from a dokku-graphite
# instance running on ifill as https://stats.ifill.tarbell.mediacloud.org/

# Also used to make mcweb-staging, running on steinam (SIC) visible.

SCRIPT_DIR=$(dirname $0)
COMMON_SH=$SCRIPT_DIR/common.sh
INSTANCE=ignored
if [ ! -f $COMMON_SH ]; then
    echo cannot find $COMMON_SH 1>&2
    exit 1
fi
. $COMMON_SH

# app name on bastion server (ie; appname.servername)
PROXY_APP=$1

REMOTE_HOST=$2
REMOTE_PORT=${3:-80}

if [ "x$PROXY_APP" = x -o \
	"x$REMOTE_HOST" = x -o \
	"x$REMOTE_PORT" = x ]; then
    echo "Usage: $0 PROXY_APP_NAME REMOTE_HOST [ REMOTE_PORT ]" 1>&2
    exit 1
fi

# 2024-05-09: nginx on tarbell startup failing when DNS name used!
if ! expr "$REMOTE_HOST" : '^[1-9][0-9]*\.[1-9][0-9]*\.[1-9][0-9]*\.[1-9][0-9]*$' >/dev/null; then
    echo "Use IP address for remote server"
    exit 1
fi

HOST=$(hostname -s)
DOMAIN=$HOST.mediacloud.org

# XXX test if $PROXY_APP.$DOMAIN resolves to a public addr in hostname -I?

if ! public_server; then
    echo "Needs to run on an Internet accessible server" 1>&2
    exit 1
fi

if dokku apps:list | grep -F -x $PROXY_APP >/dev/null; then
    echo Dokku app $PROXY_APP exists
    exit 1
fi

# create the app
dokku apps:create $PROXY_APP

# set the builder to the null builder, which does nothing
dokku builder:set $PROXY_APP selected null

# set the scheduler to the null scheduler, which does nothing

# for dokku 0.25.x
#dokku config:set $PROXY_APP DOKKU_SCHEDULER=null

# for dokku 0.26+
dokku scheduler:set $PROXY_APP selected null

# set the static-web-listener network property to the ip:port combination for remote
dokku network:set $PROXY_APP static-web-listener $REMOTE_HOST:$REMOTE_PORT

# set the port map
dokku proxy:ports-set $PROXY_APP http:80:$REMOTE_PORT

# set the domains desired
dokku domains:set $PROXY_APP $PROXY_APP.$DOMAIN

# build the (ngnix) proxy config
dokku proxy:build-config $PROXY_APP

# no global setting on tarbell?
dokku config:set $PROXY_APP DOKKU_LETSENCRYPT_EMAIL=system@mediacloud.org

# enable letsencrypt certificate creation
dokku letsencrypt:enable $PROXY_APP

echo "NOTE!!!! Make sure $PROXY_APP.$DOMAIN is accepted at $REMOTE_HOST!!!"
echo "ie; for a dokku app run 'dokku domain:add LOCAL-APP-NAME $PROXY_APP.$DOMAIN'"

# for a dokku app:
#	dokku domains:set $APP $PROXY_APP.$BASTION.$PUBLIC_DOMAIN
# for a docker-graphite service:
#	dokku graphite:nginx-expose $PROXY_APP.$BASTION.$PUBLIC_DOMAIN

