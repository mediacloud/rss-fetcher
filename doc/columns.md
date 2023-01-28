# Explanations of database columns for users of search.mediacloud.org

The following are descriptions of rss-fetcher database columns that
are (or might be) displayed in the search.mediacloud.org web application.

# Feeds

Columns copied/updated from search.mediacloud.org database:

* id - feed id
* sources_id - source id
* name - feed name
* url - rss feed URL
* active - whether feed is administratively enabled
* created_at - date/time feed was added

Generated/Internal data (subject to change):

* last_fetch_attempt - UTC (GMT) date/time of last fetch attempt (may be empty if not yet attempted).
* last_fetch_success - UTC date/time of last successful fetch (may be empty if not yet succeeded).
	NOTE! success only means that data was successfully retrieved, not that it
	was valid a RSS/Atom/RDF document.
* last_fetch_hash - MD5 checksum of the last document fetched (used to detect if the document has changed).
* last_fetch_failures - indication of how many times a fetch (and parse) have failed.
	+ "Hard" errors (one unlikely to change over time) increment last_fetch_failures by 1
	+ "Soft" errors (ones more likely to change over time) increment last_fetch_failures by 0.5
	+ "Temporary" errors (ones VERY likely to change over time) increment last_fetch_failures by 0.25
* http_etag - HTTP "ETag" header value returned by last fetch (used to prevent fetching unchanged documents).
* http_last_modified - HTTP "Last-Modified" header value returned by last fetch (used to prevent fetching unchanged documents).
	Stored (and sent back) exactly as provided by feed HTTP server.
	Format and time zone may vary.
* next_fetch_attempt - UTC date/time of next time to attempt a fetch (may be empty if just added).
* queued - Feed has will be fetched soon (typ. within a few minutes).
* system_enabled - Set to False, to disable fetching if next_fetch_attempt has exceeded configured threshold value.
* update_minutes - Number of minutes between document updates (published in feed. empty if no value published).
* http_304 - True if feed HTTP server has ever returned HTTP 304 "Not Modified" in response to an ETag or Last-Modified value we provided.
* system_status - A short string indicating status from the last fetch attempt:
	+ DNS error
	+ HTTP nnn Description
	+ SSL error
	+ Working
	+ connect timeout
	+ connection error
	+ fetch error
	+ job timeout
	+ parse error
	+ read timeout
	+ too many redirects
	+ unknown hostname
* last_new_stories - UTC date/time of the last time new stories successfully fetched, parsed and stored.
* rss_title - Title of feed parsed from fetched document (may change every day!)
* poll_minutes - Minutes between fetches.  Currently only set automatically,
	to a fixed value for feeds that often return no previously seen articles.

# Fetch Events

* created_at - UTC date/time of creation of row.
* feed_id - feed id number
* event - event type, one of:
	+ `queued`
	+ `fetch_succeeded`
	+ `fetch_failed`
	+ `fetch_disabled` - fetch failed, and system_enabled set to FALSE.
* note - description of reason fetch failed. Consists of two parts:
	the value reported in system_status optionally followed by a semicolon
	and detail information (often the representation of a Python exception)
	useful to technical folks to diagnose the issue.

	+ With `fetch_succeeded`:
		- `N skipped / N added`
		- `not modified` -- HTTP server returned 304 "Not Modified" status
		- `same hash` -- document did not change

	+ With `parse failed`:
		- `Exception('empty')` -- returned document was empty
		- `Exception('html?')` -- returned document appeared to be HTML
		- `Exception('no version')` -- type/version (Atom/rss 1.0/rss 2.0/rdf) of returned document could not be detected.
