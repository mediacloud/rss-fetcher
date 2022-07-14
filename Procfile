web: uvicorn server:app --timeout-keep-alive 500 --host 0.0.0.0 --port 8000
worker: celery -A fetcher worker -l debug --concurrency=16
fetcher: python -m scripts.queue_feeds
generator: python -m scripts.gen_daily_story_rss
