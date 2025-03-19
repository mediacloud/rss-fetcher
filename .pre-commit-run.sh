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
if [ -n "$VIRTUAL_ENV" ]; then
    TMP=$VIRTUAL_ENV/pyproject.toml
else
    echo "$0: VIRTUAL_ENV not set; see $LOG" 1>&2
    exit 1
fi
echo TMP $TMP >> $LOG

# check saved copy of pyproject.toml to see if it has changed (or does
# not yet exist) and if (re)install pre-commit optional dependencies if
# needed.
if cmp -s pyproject.toml $TMP; then
    echo no change to pyproject.toml >> $LOG
else
    echo installing pre-commit optional dependencies >> $LOG
    # --editable skips installing project package
    if python3 -m pip install --editable '.[pre-commit]'; then
	cp -p pyproject.toml $TMP
	echo done >> $LOG
    else
	STATUS=$?
	echo pip failed $STATUS >> $LOG
	exit $STATUS
    fi
fi
#pip list >> $LOG
# NOTE! first arg must be command to invoke!
"$@"
