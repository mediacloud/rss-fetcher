Change Log
==========

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