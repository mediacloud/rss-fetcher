#!/bin/sh
# Phil Budne, October 2022
# from https://dokku.com/blog/2021/dokku-0.25.0/

LOCAL_APP=$1
REMOTE_HOST=$2
REMOTE_PORT=$3

if [ "x$LOCAL_APP" = x -o \
	"x$REMOTE_HOST" = x -o \
	"x$REMOTE_PORT" = x ]; then
    echo "Usage: $0 LOCAL_APP_NAME REMOTE_HOST REMOTE_PORT" 1>&2
    exit 1
fi

HOST=$(hostname -s)
DOMAIN=$HOST.mediacloud.org
if [ "x$HOST" != xtarbell ]; then
    echo "Needs to be run on tarbell (Internet accessible server)" 1>&2
#    exit 1
fi

# XXX test if $LOCAL_APP.$DOMAIN resolves to an addr in hostname -I?
if [ x`whoami` != xroot ]; then
    alias dokku="ssh dokku@$HOST"
fi

if dokku apps:list | grep -F -x $LOCAL_APP >/dev/null; then
    echo Dokku app $LOCAL_APP exists
    exit 1
fi

# create the app
dokku apps:create $LOCAL_APP

# set the builder to the null builder, which does nothing
dokku builder:set $LOCAL_APP selected null

# set the scheduler to the null scheduler, which does nothing

# for dokku 0.25.x
#dokku config:set $LOCAL_APP DOKKU_SCHEDULER=null

# for dokku 0.26+
dokku scheduler:set $LOCAL_APP selected null

# set the static-web-listener network property to the ip:port combination for remote
dokku network:set $LOCAL_APP static-web-listener $REMOTE_HOST:$REMOTE_PORT

# set the port map
dokku proxy:ports-set $LOCAL_APP http:80:$REMOTE_PORT

# set the domains desired
dokku domains:set $LOCAL_APP $LOCAL_APP.$DOMAIN

# build the (ngnix) proxy config
dokku proxy:build-config $LOCAL_APP

# no global setting on tarbell?
dokku config:set $LOCAL_APP DOKKU_LETSENCRYPT_EMAIL=system@mediacloud.org

# enable letsencrypt certificate creation
dokku letsencrypt:enable $LOCAL_APP

echo "NOTE!!!! Make sure $LOCAL_APP.$DOMAIN is accepted at $REMOTE_HOST!!!"
