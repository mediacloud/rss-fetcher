#!/usr/bin/env bash

# use PORT if supplied (by Dokku)
uvicorn server:app --timeout-keep-alive 500 --host 0.0.0.0 --port ${PORT:-8000}
