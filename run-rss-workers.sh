#!/bin/sh
python -m scripts.clear_queue
celery -A fetcher worker -l debug --concurrency=16
