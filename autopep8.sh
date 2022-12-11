#!/bin/sh
# skip migrations directory, virtual env (created by mypy.sh)
find . -name versions -prune -o \
     -name venv\* -prune -o \
     -name \*.py -print | xargs -r autopep8 -a -i
