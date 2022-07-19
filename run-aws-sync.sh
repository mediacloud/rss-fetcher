#!/bin/sh
aws s3 sync /home/mediacloud/rss-fetcher/ s3://mediacloud-public/backup-daily-rss/
