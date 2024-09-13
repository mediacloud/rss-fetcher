#!/bin/sh

# Deploy code by pushing current branch to Dokkku app instance
# (development, staging, or production, depending on branch name)
# Phil Budne, September 2022, updated September 2024 (from web-search)!

PUSH_FLAGS=
# RSS_FETCHER_UNPUSHED inherited from environment
for ARG in $*; do
    case "$ARG" in
    --force-push) PUSH_FLAGS=--force;; # force push code to dokku repo
    --unpushed|-u) RSS_FETCHER_UNPUSHED=1;; # allow unpushed repo for devpt
    *) echo "$0: unknown argument $ARG"; exit 1;;
    esac
done

BRANCH=$(git branch --show-current)

# works when su'ed to another user or invoked via ssh
UNAME=$(whoami)

# before common.sh
case $BRANCH in
prod|staging)
    INSTANCE=$BRANCH;;
*)
    INSTANCE=$UNAME;;
esac


SCRIPT_DIR=$(dirname $0)
COMMON_SH=$SCRIPT_DIR/common.sh
if [ ! -f $COMMON_SH ]; then
    echo cannot find $COMMON_SH 1>&2
    exit 1
fi
. $COMMON_SH

check_not_root

# tmp files to clean up on exit
TMPDIR=$(pwd)/push-tmp-$$
trap "rm -rf $TMPDIR" 0
rm -rf $TMPDIR
mkdir $TMPDIR
chmod 700 $TMPDIR

# temp files: inside TMPDIR!
REMOTES=$TMPDIR/remotes

# hostname w/o any domain
HOSTNAME=$(hostname --short)

if ! git diff --quiet; then
    echo 'local changes not checked in' 1>&2
    # XXX display diffs, or just dirty files??
    exit 1
fi

# For someone that works on a branch in mediacloud repo,
# "origin" is the MCREMOTE....
ORIGIN="origin"

# PUSH_TAG_TO: other remotes to push tag to
PUSH_TAG_TO="$ORIGIN"

git remote -v > $REMOTES

case "$BRANCH" in
prod|staging)
    # check if corresponding branch in mediacloud acct up to date

    # get remote for mediacloud account
    # ONLY match ssh remote, since will want to push tag.
    # XXX need SRC_REPO_ORG!!
    MCREMOTE=$(awk '/github\.com:mediacloud\// { print $1; exit }' $REMOTES)
    if [ "x$MCREMOTE" = x ]; then
	echo could not find an ssh git remote for mediacloud org repo
	exit 1
    fi

    # check if MCREMOTE up to date.
    #    XXX sufficient if current commit part of remote branch???
    #
    #    http://codecook.io/git/214/check-if-specific-commit-is-on-remote
    #    "git branch -r --contains commit_sha" lists branches?
    #
    #    https://stackoverflow.com/questions/5549479/git-check-if-commit-xyz-in-remote-repo
    #    has "git log --cherry-pick --left-right <commitish> ^remote/branchname"
    if git diff --quiet $BRANCH $MCREMOTE/$BRANCH --; then
	echo "$MCREMOTE $BRANCH branch up to date."
    else
	# pushing to mediacloud repo should NOT be optional
	# for production or staging!!!
	echo "$MCREMOTE $BRANCH branch not up to date. run 'git push' first!!"
	exit 1
    fi
    # push tag back to JUST github mediacloud branch
    # (might be "origin", might not)
    PUSH_TAG_TO="$MCREMOTE"
    ;;
*)
    # check if origin (ie; user github fork) not up to date
    if [ "x$RSS_FETCHER_UNPUSHED" = x ]; then
	if git diff --quiet origin/$BRANCH -- 2>/dev/null; then
	    echo "origin/$BRANCH up to date"
	else
	    # have an option to override this??
	    echo "origin/$BRANCH not up to date.  push!"
	    exit 1
	fi
    fi
    ;;
esac

if ! dokku apps:exists "$APP" >/dev/null 2>&1; then
    echo "app $APP not found" 1>&2
    exit 1
fi

# DOKKU_GIT_REMOTE: Name of git remote for Dokku instance
TAB='	'
if ! grep "^$DOKKU_GIT_REMOTE$TAB" $REMOTES >/dev/null; then
    echo git remote $DOKKU_GIT_REMOTE not found 1>&2
    exit 1
fi

# before check for no changes!
echo checking $INSTANCE_HASH_VAR
INSTANCE_SH_CURR_GIT_HASH=$(dokku config:get $APP $INSTANCE_HASH_VAR)
INSTANCE_SH_FILE_GIT_HASH=$(instance_sh_file_git_hash)
if [ "x$INSTANCE_SH_CURR_GIT_HASH" != "x$INSTANCE_SH_FILE_GIT_HASH" ]; then
    echo $APP $INSTANCE_HASH_VAR $INSTANCE_SH_CURR_GIT_HASH 1>&2
    echo does not match $INSTANCE_SH hash $INSTANCE_SH_FILE_GIT_HASH 1>&2
    echo re-run $INSTANCE_SH create $INSTANCE 1>&2
    exit 1
fi

git fetch $DOKKU_GIT_REMOTE
if git diff --quiet $BRANCH $DOKKU_GIT_REMOTE/$DOKKU_GIT_BRANCH --; then
    echo no code changes
    export NO_CODE_CHANGES=1
fi

# XXX log all commits not in Dokku repo??
echo "Last commit:"
git log -n1

# XXX display URL for DOKKU_GIT_REMOTE??
echo ''
echo -n "Push branch $BRANCH to $DOKKU_GIT_REMOTE dokku app $APP? [no] "
read CONFIRM
case "$CONFIRM" in
[yY]|[yY][eE][sS]) ;;
*) echo '[cancelled]'; exit;;
esac

DATE_TIME=$(date -u '+%F-%H-%M-%S')
if [ "x$BRANCH" = xprod ]; then
    # XXX check if pushed to github/mediacloud/PROJECT prod branch??
    # (for staging too?)

    TAG=v$(grep '^VERSION' fetcher/__init__.py | sed -e 's/^.*= *//' -e 's/"//g' -e "s/'//g" -e 's/#.*//' -e 's/ *$//')
    echo "Found version number: $TAG"

    CONFIG_TAG=${TAG}
    if [ "x$NO_CODE_CHANGES" = x ]; then
	# NOTE! fgrep -x (-F -x) to match literal whole line (w/o regexps)
	if git tag | grep -F -x "$TAG" >/dev/null; then
	    echo "found local tag $TAG: update mcweb.settings.VERSION?"
	    exit 1
	fi
    else
	# here with no code change, $TAG should already exist on code & config
	# new tag for config:
	CONFIG_TAG=${CONFIG_TAG}-${DATE_TIME}
    fi

    # https://stackoverflow.com/questions/5549479/git-check-if-commit-xyz-in-remote-repo
    for REMOTE in origin $DOKKU_GIT_REMOTE $MCREMOTE; do
	if git fetch $REMOTE $TAG >/dev/null 2>&1; then
	    echo "found $REMOTE tag $TAG: update fetcher.VERSION?"
	    exit 1
	fi
    done

    echo -n "This is production! Type YES to confirm: "
    read CONFIRM
    if [ "x$CONFIRM" != 'xYES' ]; then
       echo '[cancelled]'
       exit
    fi
else
    # used to use APP instead of INSTANCE
    TAG=$DATE_TIME-$HOSTNAME-$INSTANCE
    CONFIG_TAG=${TAG}		# only used for staging
fi
echo ''
echo adding local tag $TAG
git tag $TAG

# NOTE: push will complain if you (developer) switch branches
# (or your branch has been perturbed upstream, ie; by a force push)
# so add script option to enable --force to push to dokku git repo?

# NOTE! pushing tag first time causes mayhem (reported by Rahul at
# https://github.com/dokku/dokku/issues/5188)
#
# perhaps explained by https://dokku.com/docs/deployment/methods/git/
#	"As of 0.22.1, Dokku will also respect the first pushed branch
#	as the primary branch, and automatically set the deploy-branch
#	value at that time."
# (ISTR seeing refs/tags/..../refs/tags/....)

################
# takes any number of VAR=VALUE pairs
# values with spaces probably lose!!!!!!
EXTRAS=
add_extras() {
    for x in $*; do
	EXTRAS="$EXTRAS -S $x"
    done
}

add_extras DOKKU_WAIT_TO_RETIRE=30
add_extras DOKKU_DEFAULT_CHECKS_WAIT=5

# display/log time in UTC:
add_extras TZ=UTC

# using automagic STATSD_URL in fetcher/stats.py
add_extras STATSD_PREFIX=mc.${INSTANCE}.rss-fetcher

case $BRANCH in
prod|staging)
    # always do fresh clone of config repo main branch
    cd $TMPDIR
    echo cloning $CONFIG_REPO_NAME repo 1>&2
    if ! git clone $CONFIG_REPO_PREFIX/$CONFIG_REPO_NAME.git >/dev/null 2>&1; then
	echo "could not clone config repo" 1>&2
	exit 1
    fi
    cd ..
    PRIVATE_CONF_REPO=$TMPDIR/$CONFIG_REPO_NAME

    # always read prod first
    PRIVATE_CONF_FILE=$PRIVATE_CONF_REPO/prod.sh
    # use staging.sh (if present) for overrides on staging:
    if [ "x$BRANCH" = xstaging -a -f $PRIVATE_CONF_REPO/staging.sh ]; then
	CONFIG_EXTRAS="$CONFIG_EXTRAS -F $PRIVATE_CONF_REPO/staging.sh"
    fi
    tag_conf_repo() {
	(
	    cd $PRIVATE_CONF_REPO
	    echo tagging $CONFIG_REPO_NAME
	    git tag $CONFIG_TAG
	    echo pushing tag $CONFIG_TAG
	    # freshly cloned, so upstream == origin
	    git push origin $CONFIG_TAG
	)
    }
    ;;

*)
    PRIVATE_CONF_FILE=.env.template
    USER_CONF=.pw.$UNAME
    if [ ! -f $USER_CONF ]; then
	echo generating rss-fetcher API user/password, saving in $USER_CONF
	echo RSS_FETCHER_USER=$INSTANCE$$ > $USER_CONF
	echo RSS_FETCHER_PASS=$(openssl rand -base64 15) >> $USER_CONF
	chmod 600 $USER_CONF
    fi
    # unset DATABASE/REDIS URLs from .env-template, read user override file
    CONFIG_EXTRAS="$CONFIG_EXTRAS -F $USER_CONF -U DATABASE_URL"
    alias tag_conf_repo=false
    ;;
esac

if public_server; then
    # not in global config on tarbell:
    add_extras DOKKU_LETSENCRYPT_EMAIL=$DOKKU_LETSENCRYPT_EMAIL
fi

# used in fetcher/__init__.py to set APP
# ('cause I didn't see it available any other way -phil)
add_extras MC_APP=$APP

case "$INSTANCE" in
prod|staging)
    SAVEDIR=$(pwd)
    mkdir $TMPDIR
    chmod 700 $TMPDIR
    cd $TMPDIR
    if ! git clone $CONFIG_REPO_PREFIX/$CONFIG_REPO_NAME.git >/dev/null 2>&1; then
	echo could not clone config repo 1>&2
	exit 1
    fi
    cd "$SAVEDIR"
    VARS_FILE=$TMPDIR/$CONFIG_REPO_NAME/prod.sh
    # if staging read staging.sh too!

    add_extras RSS_FETCH_WORKERS=16
    if [ "x$INSTANCE" = xprod ]; then
	# production only settings
	# (have staging.sh file to override??)

	# story retention, RSS file (re)generation:
	add_extras RSS_OUTPUT_DAYS=90
    fi
    ;;
*)
    VARS_FILE=.pw.$INSTANCE
    if [ -f $VARS_FILE ]; then
	echo using rss-fetcher API user/password in $VARS_FILE
    else
	# XXX create from .env.template??
	echo generating rss-fetcher API user/password, saving in $VARS_FILE
	echo RSS_FETCHER_USER=$INSTANCE$$ > $VARS_FILE
	echo RSS_FETCHER_PASS=$(openssl rand -base64 15) >> $VARS_FILE
    fi
    chmod 600 $VARS_FILE
    ;;
esac

################

echo checking dokku config...
$SCRIPT_DIR/config.sh $INSTANCE $PRIVATE_CONF_FILE $CONFIG_EXTRAS $EXTRAS

CONFIG_STATUS=$?
case $CONFIG_STATUS in
$CONFIG_STATUS_CHANGED)
    if [ "x$NO_CODE_CHANGES" != x ]; then
	tag_conf_repo
	echo 'config updated; no code changes' 1>&2
	exit 0
    fi
    ;;
$CONFIG_STATUS_ERROR)
    echo config script failed 1>&2
    exit 1
    ;;
$CONFIG_STATUS_NOCHANGE)
    if [ "x$NO_CODE_CHANGES" != x ]; then
	echo no changes to code or config 1>&2
	exit 1
    fi
    ;;
*)
    echo $0: unknown CONFIG_STATUS $CONFIG_STATUS 1>&2
    exit 1
esac

################

echo ''
echo stopping processes...
dokku ps:stop $APP

echo ''
CURR_GIT_BRANCH=$(dokku git:report $APP | awk '/Git deploy branch:/ { print $4 }')
if [ "x$CURR_GIT_BRANCH" != "x$DOKKU_GIT_BRANCH" ]; then
    echo "Setting $APP deploy-branch to $DOKKU_GIT_BRANCH"
    dokku git:set $APP deploy-branch $DOKKU_GIT_BRANCH
fi

# output on multiple lines? show remote URL??
echo "pushing branch $BRANCH to $DOKKU_GIT_REMOTE $DOKKU_GIT_BRANCH"
if git push $PUSH_FLAGS $DOKKU_GIT_REMOTE $BRANCH:$DOKKU_GIT_BRANCH; then
    echo OK
else
    STATUS=$?
    echo "$0: git push $DOKKU_GIT_REMOTE $BRANCH:$DOKKU_GIT_BRANCH failed with status $STATUS" 2>&1
    echo "deleting local tag $TAG"
    git tag -d $TAG >/dev/null 2>&1
    exit $STATUS
fi

echo "pushing tag $TAG to $DOKKU_GIT_REMOTE"
# suppress "WARNING: deploy did not complete, you must push to main."
git push $DOKKU_GIT_REMOTE $TAG >/dev/null 2>&1
echo "================"

# push tag to upstream repos
for REMOTE in $PUSH_TAG_TO; do
    echo pushing tag $TAG to $REMOTE
    git push $REMOTE $TAG
    echo "================"
done

# for prod/staging: tag config repo and push tag
if [ -n "$PRIVATE_CONF_REPO" -a -d "$PRIVATE_CONF_REPO" ]; then
    tag_conf_repo
fi

# start fetcher/worker processes (only needed first time)
echo scaling up
PROCS="fetcher=1 web=1"
dokku ps:scale --skip-deploy $APP $PROCS
# never needed?
dokku ps:start $APP

echo "$DATE_TIME $APP $REMOTE $TAG" >> push.log
