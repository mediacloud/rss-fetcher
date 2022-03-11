web: gunicorn -w 1 -k gevent --timeout 500 server:app
worker: celery -A fetcher worker -l info --concurrency=8
fetcher: python -m scripts.queue_feeds
