#!/bin/bash
# "predeploy" script (see app.json) invoked by dokku
echo cwd `pwd`
alembic upgrade head
