#!/bin/sh

# Invoked from .pre-commit-config.yaml to run mypy (or other tool)
# using "pre-commit" variable in pyproject.toml file
# project.optional-dependencies section.

# from mc-providers, from es-tools, from sitemap-tools

# NOTE!! Takes FULL command line as arguments
LOG=$0.log
(
  date
  pwd
  echo COMMAND LINE: $0 $*
  echo '#####'
  echo ENVIRONMENT:
  env
  echo '#####'
) > $LOG

# NOTE!! https://github.com/pre-commit/mirrors-mypy/README.md says
# "using the --install-types is problematic." (mutates cache)

# Want to stash copy of pyproject.toml in the top level of the
# pre-commit created virtual environment to detect changes.
# Fortunately, a useful variable points there!
if [ -z "$VIRTUAL_ENV" ]; then
    echo "$0: VIRTUAL_ENV not set; see $LOG" 1>&2
    exit 1
fi

# check if package lists have changed, and re-install if needed:
check_install() {
    FN=$1
    shift

    TMP=$VIRTUAL_ENV/.$FN
    echo TMP $TMP >> $LOG
    if cmp -s $FN $TMP; then
	echo no change to $FN >> $LOG
    else
	echo installing deploy optional dependencies >> $LOG
	if python3 -m pip install $*; then
	    cp -p $FN2 $TMP2
	else
	    STATUS=$?
	    echo pip failed $STATUS for $FN2 >> $LOG
	    exit $STATUS
	fi
    fi
}

# NOTE! using pip-tools generated requirements.txt
# (and installs this package), its requiremnets
# and packages needed for pre-commit (mypy):
check_install pyproject.toml --editable '.[pre-commit]'

# for linting deploy.py
check_install req-deploy.txt -r req-deploy.txt

#pip list >> $LOG
# NOTE! first arg must be command to invoke!
"$@"
