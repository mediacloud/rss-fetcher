#!/bin/sh
# "predeploy" script (see app.json) invoked by dokku, run in /app
alembic upgrade head
