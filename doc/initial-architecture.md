Backup RSS Fetcher
==================

Tables
-----

## Feeds

Columns:

* id: bigint PK
* mc_feeds_id: bigint
* mc_media_id: bigint
* name: str
* url: str
* last_fetch_attempt: datetime
* last_fetch_success: datetime
* last_fetch_hash: str

Indexes:
* last_attempt
* last_success

## Stories

* id: bigint PK
* mc_feeds_id: bigint
* mc_media_id: bigint
* url: str
* guid: str
* pub_date: datetime
* fetched_at: datetime
* domain: str

Components
----------

## Cron Job

```
Select feeds we haven't checked for a day, sorted by oldest, up to 5000:
  update last fetch_attempt
  queue feed for fetching
```

## Fetch Task

```
Fetch content of feed url
if success:
  update last_success
  compute file hash
  if hash is new:
    for story in feed:
      insert story into database
```
