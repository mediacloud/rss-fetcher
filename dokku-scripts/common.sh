# This is a -*-shell-script-*-
# Put local settings into local.sh (which never exists in mediacloud repo)!
# common settings for dokku-scripts directory
# (things that may change between Ubuntu releases and docker/doku dists)

if [ "x$SCRIPT_DIR" = x ]; then
   echo "common.sh: SCRIPT_DIR not set!!!"
   exit 1
fi

if [ "x$INSTANCE" = x ]; then
   echo "common.sh: INSTANCE not set!!!"
   exit 1
fi

BASE_APP=rss-fetcher

HOST=$(hostname -s)
# local access:
FQDN=$(hostname -f)

# should be set/used to source this!
COMMON_SH=$SCRIPT_DIR/common.sh

################
# hosts etc

# Internet visible host (for proxying)
BASTION=tarbell

# Internet domain where BASTION is visible
PUBLIC_DOMAIN=mediacloud.org

# wildcard *.$BASTION.$PUBLIC_DOMAIN should point
# to $BASTION.$PUBLIC_DOMAIN!!!

DOKKU_LETSENCRYPT_EMAIL=system@mediacloud.org

# put this one place, in case run on a cluster
# where all servers are Internet visible
# (used to test whether a letsencrypt cert can be gotten)

public_server() {
    # if all servers are Internet visible define
    # replace this with "true", and set BASTION=$(hostname -s)!!
    test "x$(hostname -s)" = "x$BASTION"
}

################################################################
# directory for .list files
APT_SOURCES_LIST_D=/etc/apt/sources.list.d
# directory for (dearmoured/binary) .gpg files
APT_KEYRINGS_D=/etc/apt/keyrings

# Names of package sources to add to apt.
# Each name should be lower case, for use in sources.list and keyring files,
# and have upper case variable names declared below:
#  NAME_URL: URL for directory with .deb files
#  DOCKER_GPG_URL: url for gpg key file
#  DOCKER_COMPONENTS: component names for .list file "deb" line
SOURCES="docker dokku"

DOCKER_URL=https://download.docker.com/linux/ubuntu
DOCKER_GPG_URL="$DOCKER_URL/gpg"
DOCKER_COMPONENTS="stable"

DOKKU_BASE_URL=https://packagecloud.io/dokku/dokku
DOKKU_URL="$DOKKU_BASE_URL/ubuntu"
DOKKU_GPG_URL="$DOKKU_BASE_URL/gpgkey"
DOKKU_COMPONENTS="main"

################

# host server location of storage dirs
STORAGE_HOME=/var/lib/dokku/data/storage

# UGH! extract from fetcher/path.py OUTPUT_RSS_DIR???
RSS_OUTPUT_DIR=rss-output-files

################
# stats

# single dokku service instance per host:
if public_server; then
    # services cannot get letsencrypt certificates, only apps can, so make
    # an obscure service name; create-stats.sh will use stats-service-proxy.sh to
    # create a "stats" app which proxies to the service.
    GRAPHITE_STATS_SVC=ObscureStatsServiceName
else
    # Could use obscure name on private servers too, since public
    # access to them is ALSO proxied (via http-proxy.sh), but ifill is
    # already set up with the service named stats;
    GRAPHITE_STATS_SVC=stats
fi
################
# misc functions

if [ x$(whoami) = xroot ]; then
    alias check_root=true
    check_not_root() {
	if [ x`whoami` != xroot ]; then
	    echo "$0 must not be run as root" 1>&2
	    exit 1
	fi
    }
else
    # NOTE! can't use localhost for ssh if user home directories NFS
    # shared across servers (or else it will look like the host
    # identity keeps changing)
    alias dokku="ssh dokku@$(hostname)"
    alias check_not_root=true
    check_root() {
	echo "$0 must be run as root" 1>&2
	exit 1
    }
fi

################

LOCAL_SH=$SCRIPT_DIR/local.sh
if [ -f $LOCAL_SH ]; then
    echo reading $LOCAL_SH
    . $LOCAL_SH
fi

if [ "x$INSTANCE" = xprod ]; then
    APP=$BASE_APP
else
    # INSTANCE is staging or username
    # consistent with story-indexer and rss-fetcher ordering:
    APP=${INSTANCE}-${BASE_APP}
fi

# name of deploy branch in DOKKU_GIT_REMOTE repo
DOKKU_GIT_BRANCH=main

# git remote for app; created by instance.sh, used by push.sh
# (web-search uses mcweb (app name))
DOKKU_GIT_REMOTE=dokku_$INSTANCE

# exit status of config.sh
CONFIG_STATUS_CHANGED=0
CONFIG_STATUS_ERROR=1
CONFIG_STATUS_NOCHANGE=2

INSTANCE_SH=$SCRIPT_DIR/instance.sh
# name of dokku config var set by instance.sh, checked by push.sh:
INSTANCE_HASH_VAR=INSTANCE_SH_GIT_HASH

# function and variable name are now misleading;
# return value is the concatenation of the short hashes of
# instance.sh AND this file!!
instance_sh_file_git_hash() {
    IHASH=$(git log -n1 --oneline --no-abbrev-commit --format='%h' $INSTANCE_SH)
    CHASH=$(git log -n1 --oneline --no-abbrev-commit --format='%h' $COMMON_SH)
    if [ -f $LOCAL_SH ]; then
	LHASH=$(git log -n1 --oneline --no-abbrev-commit --format='%h' $LOCAL_SH 2>/dev/null)
    fi
    echo $IHASH$CHASH$LHASH
}
