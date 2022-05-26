Change Log
==========

## v0.7.0

Check a normalized story URL and title for uniqueness before saving, like we do on our production system. This is a 
critical de-duplication step.

## v0.6.1

Generate files for yesterday (not 2 days ago) because that will make delivered results more timely. 

## v0.6.0

Add in new feed. Prep to show some data on website. 

## v0.5.5

More work on concurrency for prod server and related configurations. 

## v0.5.4

Tweaks to RSS file generation to make it more robust.

## v0.5.3

Query bug fix.

## v0.5.2

Handle podcast feeds, which don't have links by ignoring them in reporting script (they have enclosures instead)

## v0.5.1

Deployment work for generating daily rss files.

## v0.5.0

Retry feeds that we tried by didn't respond (up to 3 times in a row before giving up).

## v0.4.0

Update dependencies to latest

## v0.3.2

RSS path loaded from env-var

## v0.3.1

Ignore a whole bunch of errors that are expected ones

## v0.3.0

Add title and canonical domain to daily feeds 

## v0.2.1

Move max feeds to fetch at a time limit to an env var for easier config (`MAX_FEEDS` defaults to 1000)

## v0.2.0

Restructured queries to try and solve DB connection leak bug. 

## v0.1.2

Production performance-related tweaks.

## v0.1.1

Make sure duplicate story urls don't get inserted (no matter where they are from). This is the quick solution to making
sure an RSS feed with stories we have already saved doesn't create duplicates.

## v0.1.0

First release, seems to work.
