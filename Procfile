web: ./run-server.sh
fetcher: ./run-fetch-rss-feeds.sh --loop 1
worker: ./run-rss-workers.sh
generator: ./run-gen-daily-story-rss.sh
archiver: python -m scripts.db_archive
update: python -m scripts.update_feeds
