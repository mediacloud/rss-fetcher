#!/usr/bin/env bash

# uses PORT if supplied (by Dokku)
python -m scripts.server "$@"
