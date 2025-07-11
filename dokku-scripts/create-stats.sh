#!/bin/sh

# create a dokku-graphite service
# (can be used with any dokku app)
# Phil Budne, October 2022

# NOTE: 2025-07-11: no longer invoked by rss-fetcher scripts
# (move this, or simplified version to system-dev-ops/monitoring ??)

INSTANCE=$1
shift

if [ "x$INSTANCE" = x ]; then
    echo "$0 INSTANCE [ APP_TO_LINK ]" 1>&2
    exit 1
fi

# optional:
LINK_TO_APP=$1

SCRIPT_DIR=$(dirname $0)
COMMON_SH=$SCRIPT_DIR/common.sh
INSTANCE=ignored
if [ ! -f $COMMON_SH ]; then
    echo cannot find $COMMON_SH 1>&2
    exit 1
fi
. $COMMON_SH

HOST=$(hostname -s)

if dokku graphite:exists $GRAPHITE_STATS_SVC >/dev/null 2>&1; then
    echo found graphite service $GRAPHITE_STATS_SVC
else
    echo creating graphite service $GRAPHITE_STATS_SVC
    dokku graphite:create $GRAPHITE_STATS_SVC
    CREATED=1
fi

if public_server; then
    # give the encrypted service an obvious/pleasant name:
    STATS_PROXY_APP=stats
    if dokku apps:exists $STATS_PROXY_APP >/dev/null 1>&2; then
	echo found proxy app $STATS_PROXY_APP
    else
	# establish proxy app for local service letsencrypt cert
	$SCRIPT_DIR/stats-service-proxy.sh $GRAPHITE_STATS_SVC $STATS_PROXY_APP
    fi
    FULLNAME=$STATS_PROXY_APP.$(hostname -s).$PUBLIC_DOMAIN
else
    # use unencrypted service on non-public server
    # (cannot get letsencrypt cert on server that isn't Internet visible)

    if true; then
	# only available in private domain (ie; .angwin)
	FULLNAME=$GRAPHITE_STATS_SVC.$(hostname -f)
    else
	# dokku app name to create on BASTION host: ie; stats.OURHOST
	BASTION_SERVICE=$GRAPHITE_STATS_SVC.$HOST

	# expose dokku-graphite http service on port 80
	# and recognize a domain name like stats.OURHOST.tarbell.mediacloud.org
	FULLNAME=$BASTION_SERVICE.$BASTION.$PUBLIC_DOMAIN
   fi
    NGCONF=/etc/nginx/conf.d/grafana-${GRAPHITE_STATS_SVC}.conf
    if grep -F "$FULLNAME" $NGCONF >/dev/null 2>&1; then
	echo found $FULLNAME in $NGCONF
    else
	echo exposing $GRAPHITE_STATS_SVC as $FULLNAME
	dokku graphite:nginx-expose $GRAPHITE_STATS_SVC $FULLNAME

	if [ "x$BASTION_SERVICE" != x ]; then
	    # give instructions on how set up encrypted proxy on BASTION host:
	    echo "run '$SCRIPT_DIR/http-proxy.sh $BASTION_SERVICE $HOST 80' on $BASTION to make stats server public"
	fi
    fi
fi
if [ "x$LINK_TO_APP" != x ]; then
    if ! dokku graphite:linked $GRAPHITE_STATS_SVC $LINK_TO_APP >/dev/null 2>&1; then
	echo linking $GRAPHITE_STATS_SVC service to app $LINK_TO_APP
	dokku graphite:link $GRAPHITE_STATS_SVC $LINK_TO_APP
    fi
fi

if [ "x$CREATED" != x ]; then
    echo "**** connect to https://$FULLNAME user admin password admin to reset admin password ****"
fi
