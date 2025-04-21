#!/bin/sh

# uses PORT if supplied (by Dokku)
python -m scripts.server "$@"
