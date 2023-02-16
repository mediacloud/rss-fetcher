web: ./run-server.sh
# remove "--loop N" (and re-run dokku-scripts/instance.sh)
# to disable persistent fetcher process (which sends stats every minute)
fetcher: ./run-fetch-rss-feeds.sh --loop 1
worker: ./run-rss-workers.sh
# removed generator/archiver/update: now run via "dokku enter"
