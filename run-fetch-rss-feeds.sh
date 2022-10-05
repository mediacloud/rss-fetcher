#!/bin/sh
echo ==== clear_queue
python -m scripts.clear_queue
echo ==== queue_feeds
python -m scripts.queue_feeds "$@"
