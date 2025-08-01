#!/bin/sh

# apply config to Dokku app
# copied verbatim from web-search
# intended to NOT be app-specific (could live in devops repo)
# invoked from push.sh

SCRIPT_DIR=$(dirname $0)

INSTANCE=$1
shift
CONFIG_FILE=$1
shift
# remainder passed as args to vars.py

# uses INSTANCE, sets APP, defines dokku function
. $SCRIPT_DIR/common.sh

if [ -z "$INSTANCE" -o -z "$CONFIG_FILE" -o ! -f "$CONFIG_FILE" ]; then
    echo Usage: $0 INSTANCE CONFIG_FILE 1>&2
    echo '(this script is NOT meant for user invocation!)' 1>&2
    exit $CONFIG_STATUS_ERROR
fi

if [ -z "$APP" ]; then
    echo APP not set 1>&2
    exit $CONFIG_STATUS_ERROR
fi

# get current app setttings (fail out if app does not exist)
CURR=/var/tmp/curr-config$$.json
trap "rm -f $CURR" 0
if ! dokku config:export --format=json $APP > $CURR; then
    echo could not get $APP config 1>&2
    exit $CONFIG_STATUS_ERROR
fi

if [ -f dokku-scripts/.configlib/bin/dotenv ]; then
    echo removing old private dotenv install 1>&2
    rm -rf dokku-scripts/.configlib
fi
if [ ! -f venv/bin/dotenv ]; then
    echo 'need to re-run "make install" to update venv' 1>&2
    exit $CONFIG_STATUS_ERROR
fi

# takes any number of VAR=VALUE pairs
# values with spaces probably lose!!!!!!
add_extras() {
    for x in $*; do
	EXTRAS="$EXTRAS -S $x"
    done
}
# added for all instances:
# _could_ supply ..._ENV via private conf files, but supplying here makes
# values consistant, and one place to change for apps that use this script
# (if moved to devops repo).  Supplying "..._ENV" values separately per
# facility is to avoid temptation to transmogrify values in code.
add_extras "AIRTABLE_HARDWARE=$HOST" \
	   "AIRTABLE_ENV=$INSTANCE" \
	   "AIRTABLE_NAME=$INSTANCE" \
	   "SENTRY_ENV=$INSTANCE"

# NOTE! vars.py output is shell-safe; it contains only VAR=BASE64ENCODEDVALUE ...
# Want config:import! which would avoid need for base64 (--encoded) values
CONFIG_OPTIONS='--encoded'

# NO_CODE_CHANGES exported by push.sh:
if [ -z "$NO_CODE_CHANGES" ]; then
    # if code changes, don't restart before pushing
    CONFIG_OPTIONS="$CONFIG_OPTIONS --no-restart"
fi

# get dotenv package from venv; generates base64 encoded values
CONFIG_VARS=$(venv/bin/python $SCRIPT_DIR/vars.py --file $CONFIG_FILE --current $CURR $EXTRAS "$@")

if [ -z "$CONFIG_VARS" ]; then
    # nothing to set... exit stage left!
    # https://en.wikipedia.org/wiki/Snagglepuss
    exit $CONFIG_STATUS_NOCHANGE
elif dokku config:set $APP $CONFIG_OPTIONS $CONFIG_VARS; then
    exit $CONFIG_STATUS_CHANGED
else
    exit $CONFIG_STATUS_ERROR
fi
