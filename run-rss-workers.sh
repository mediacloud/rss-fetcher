#!/bin/sh
python -m scripts.clear_queue
python -m fetcher.main -A fetcher worker -l debug --concurrency=16
