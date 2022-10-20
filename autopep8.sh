#!/bin/sh
find . -name versions -prune -o -name \*.py -print | xargs autopep8 -a -i
