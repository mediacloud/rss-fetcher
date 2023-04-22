#!/bin/sh

# Deploy code by pushing current branch to Dokkku app instance
# (development, staging, or production, depending on branch name)
# Phil Budne, September 2022

# DOES NOT NEED TO BE RUN AS ROOT!!!

APP=rss-fetcher

SCRIPT_DIR=$(dirname $0)
INSTALL_CONF=$SCRIPT_DIR/install-dokku.conf
if [ ! -f $INSTALL_CONF ]; then
    echo cannot find $INSTALL_CONF 1>&2
    exit 1
fi
. $INSTALL_CONF

# tmp files to clean up on exit
REMOTES=/tmp/remotes$$
trap "rm -f $REMOTES" 0

# hostname w/o any domain
HOSTNAME=$(hostname --short)

# get logged in user (even if su(do)ing)
# (lookup utmp entry for name of tty from stdio)
# will lose if run non-interactively via ssh (no utmp entry)
LOGIN_USER=$(who am i | awk '{ print $1 }')
if [ "x$LOGIN_USER" = x ]; then
    # XXX fall back to whoami (look by uid)
    echo could not find login user 2>&1
    exit 1
fi

if ! git diff --quiet; then
    echo 'local changes not checked in' 1>&2
    # XXX display diffs, or just dirty files??
    exit 1
fi

# XXX handle options for real!!
if [ "x$1" = x--force-push ]; then
    PUSH_FLAGS=--force
elif [ "x$1" != x ]; then
    echo "Unknown argument $1" 1>&2
    exit 1
fi
BRANCH=$(git branch --show-current)

# For someone that works on a branch in mediacloud repo,
# "origin" is the MCREMOTE....
ORIGIN="origin"

# PUSH_TAG_TO: other remotes to push tag to
PUSH_TAG_TO="$ORIGIN"

# DOKKU_GIT_REMOTE: Name of git remote for Dokku instance

git remote -v > $REMOTES

case "$BRANCH" in
prod|staging)
    # check if corresponding branch in mediacloud acct up to date

    # get remote for mediacloud account
    # ONLY match ssh remote, since will want to push tag.
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
	echo "$MCREMOTE $BRANCH branch not up to date.  push first!!"
	exit 1
    fi
    # push tag back to JUST github mediacloud branch
    # (might be "origin", might not)
    PUSH_TAG_TO="$MCREMOTE"
    DOKKU_GIT_REMOTE=dokku_$BRANCH
    ;;
*)
    # check if origin (ie; user github fork) not up to date
    # XXX need "git pull" ??
    if git diff --quiet origin/$BRANCH --; then
	echo "origin/$BRANCH up to date"
    else
	# have an option to override this??
	echo "origin/$BRANCH not up to date.  push!"
	exit 1
    fi

    DOKKU_GIT_REMOTE=dokku_$LOGIN_USER
    ;;
esac

# name of deploy branch in DOKKU_GIT_REMOTE repo
DOKKU_GIT_BRANCH=main

case $BRANCH in
prod) ;;
staging) APP=staging-$APP;;
*) APP=${LOGIN_USER}-$APP;;
esac

if ! dokku apps:exists "$APP" >/dev/null 2>&1; then
    echo "app $APP not found" 1>&2
    exit 1
fi

TAB='	'
if ! grep "^$DOKKU_GIT_REMOTE$TAB" $REMOTES >/dev/null; then
    echo git remote $DOKKU_GIT_REMOTE not found 1>&2
    exit 1
fi

# before check for no changes!
echo checking INSTANCE_SH_GIT_HASH
INSTANCE_SH_CURR_GIT_HASH=$(dokku config:get pbudne-rss-fetcher INSTANCE_SH_GIT_HASH)
INSTANCE_SH_FILE_GIT_HASH=$(git_hash $SCRIPT_DIR/instance.sh)
if [ "x$INSTANCE_SH_CURR_GIT_HASH" != "x$INSTANCE_SH_FILE_GIT_HASH" ]; then
    echo $APP INSTANCE_SH_FILE_GIT_HASH $INSTANCE_SH_CURR_GIT_HASH 1>&2
    echo does not match $SCRIPT_DIR/instance.sh hash $INSTANCE_SH_FILE_GIT_HASH 1>&2
    echo re-run $SCRIPT_DIR/instance.sh create NAME 1>&2
    exit 1
fi

git fetch $DOKKU_GIT_REMOTE
# have a --push-if-no-changes option?
if git diff --quiet $BRANCH $DOKKU_GIT_REMOTE/$DOKKU_GIT_BRANCH --; then
    echo no changes 1>&2
    exit
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

if [ "x$BRANCH" = xprod ]; then
    # XXX check if pushed to github/mediacloud/PROJECT prod branch??
    # (for staging too?)

    TAG=v$(grep '^VERSION' fetcher/__init__.py | sed -e 's/^.*= *//' -e 's/"//g' -e "s/'//g")
    echo "Found version number: $TAG"

    # NOTE! fgrep -x (-F -x) to match literal whole line (w/o regexps)
    if git tag | grep -F -x "$TAG" >/dev/null; then
	echo "found local tag $TAG: update fetcher.VERSION?"
	exit 1
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
    # XXX use staging or $USER instead of full $APP for brevity?
    TAG=$(date -u '+%F-%H-%M-%S')-$HOSTNAME-$APP
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

echo ''
echo stopping processes...
dokku ps:stop $APP

echo checking dokku config...
$SCRIPT_DIR/config.sh $APP

echo ''
if git log -n1 $DOKKU_GIT_REMOTE/$DOKKU_GIT_BRANCH -- >/dev/null 2>&1; then
    # not first push, safe to push by tag name
    echo "Pushing $TAG to $DOKKU_GIT_REMOTE $DOKKU_GIT_BRANCH"
    if git push $PUSH_FLAGS $DOKKU_GIT_REMOTE $TAG:$DOKKU_GIT_BRANCH; then
	echo OK 2>&1
    else
	STATUS=$?
	echo "$0: git push failed with status $STATUS" 2>&1
	git tag -d $TAG >/dev/null 2>&1
	exit $STATUS
    fi
else
    # first push for new app, cannot push tag, or confusion ensues
    # (maybe not w/ manually configured deploy-branch??)

    echo "Setting $APP deploy-branch to $DOKKU_GIT_BRANCH"
    dokku git:set $APP deploy-branch $DOKKU_GIT_BRANCH

    echo "pushing $BRANCH to $DOKKU_GIT_REMOTE $DOKKU_GIT_BRANCH (first push)"
    if git push $DOKKU_GIT_REMOTE $BRANCH:$DOKKU_GIT_BRANCH; then
	echo OK
    else
	STATUS=$?
	echo "$0: initial git push failed with status $STATUS" 2>&1
	git tag -d $TAG >/dev/null 2>&1
	exit $STATUS
    fi
    echo "================"

    echo "First push: pushing tag $TAG"
    # suppress "WARNING: deploy did not complete, you must push to main."
    git push $DOKKU_GIT_REMOTE $TAG >/dev/null 2>&1
fi
echo "================"

# push tag to upstream repos
for REMOTE in $PUSH_TAG_TO; do
    echo pushing tag $TAG to $REMOTE
    git push $REMOTE $TAG
    echo "================"
done

# start fetcher/worker processes (only needed first time)
echo scaling up
PROCS="fetcher=1 web=1"
dokku ps:scale --skip-deploy $APP $PROCS
dokku ps:start $APP

echo "$(date '+%F %T') $APP $REMOTE $TAG" >> push.log
