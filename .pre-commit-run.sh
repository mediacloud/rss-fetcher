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

# using development venv:
. .venv/bin/activate

# NOTE! first arg must be command to invoke!
"$@"
