#!/bin/sh
celery -A fetcher worker -l debug --concurrency=8
