#!/usr/bin/env bash

uvicorn server:app --timeout-keep-alive 500 --host 0.0.0.0 --port 8000
