#!/usr/bin/env bash

uvicorn server:app --timeout-keep-alive 300 --host 0.0.0.0 --port 8000
