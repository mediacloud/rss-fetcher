#!/bin/bash
# "predeploy" script (see app.json) invoked by dokku
echo git branch $(git branch --show-current)
echo git hash $(git rev-parse --verify HEAD)
echo git tags $(git tag --points-at HEAD)
alembic upgrade head
