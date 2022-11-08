#!/bin/sh

# create a dokku-graphite service
# (can be used with any dokku app)
# Phil Budne, October 2022

# optional:
LINK_TO_APP=$1

SCRIPT_DIR=$(dirname $0)
INSTALL_CONF=$SCRIPT_DIR/install-dokku.conf
if [ ! -f $INSTALL_CONF ]; then
    echo cannot find $INSTALL_CONF 1>&2
    exit 1
fi
. $INSTALL_CONF

HOST=$(hostname -s)

if ! dokku graphite:exists $GRAPHITE_STATS_SVC; then
    dokku graphite:create $GRAPHITE_STATS_SVC

    if [ "x$HOST" = "x$BASTION" ]; then
	# establish proxy app for local service letsencrypt cert

	# not yet tested whether this is kosher:
	STATS_PROXY_APP=$GRAPHITE_STATS_SVC

	# script not yet tested!!!
	$SCRIPT_DIR/service_proxy.sh $GRAPHITE_STATS_SVC $STATS_PROXY_APP
    else
	# use unencrypted service on non-public server
	# (cannot get letsencrypt cert on server that isn't Internet visible)

	# dokku app name to create on BASTION host: ie; stats.OURHOST
	BASTION_SERVICE=$GRAPHITE_STATS_SVC.$HOST

	# expose dokku-graphite http service on port 80
	# and recognize a domain name like stats.OURHOST.tarbell.mediacloud.org
	dokku graphite:nginx-expose $GRAPHITE_STATS_SVC $BASTION_SERVICE.$BASTION.$PUBLIC_DOMAIN

	# give instructions on how set up encrypted proxy on BASTION host:
	echo "NOTE!!! run '$SCRIPT_DIR/http-proxy.sh $BASTION_SERVICE $HOST 80' on $BASTION"
    fi
fi
if [ "x$LINK_TO_APP" != x ]; then
    if ! dokku graphite:linked $GRAPHITE_STATS_SVC $LINK_TO_APP; then
	echo linking $GRAPHITE_STATS_SVC service to app $LINK_TO_APP
	dokku graphite:link $GRAPHITE_STATS_SVC $LINK_TO_APP
    fi
fi
