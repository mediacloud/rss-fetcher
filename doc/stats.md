# Statistics gathering in the RSS Fetcher

##### Phil Budne, September 29, 2022

## Motivation

The RSS Fetcher is difficult to statically test: Real-world monitored
feeds can present myriad permutations of good and bad results,
scheduling code that depends on HTTP interactions can't be trivially
tested, etc.

Adding statistics (observability) to the RSS fetcher is meant to make
it easier to test whether new code behaves "about as well" as current
production code, as well as monitor and alert on the production system.

I evaluated possible statistics monitoring systems on a number of axes:

1. Simple to install and operate
2. Cloud based versions available
3. Easy to gather statistics from multi-process workers
4. Currently maintained
5. Dokku integration

I decided on the [Dokku Graphite Plugin](https://github.com/dokku/dokku-graphite)

which uses statsd for collection, graphite (carbon/whisper) for storage,
and grafana for rendering, as the most plug-and-play solution,
although it comes out of the box with no additional (host system)
statistics (only a few related to statsd and carbon/graphite) that
means no clutter, and grafana offers great flexibility (can pull from
lots of data sources, and many dashboards are available).

The [docker-grafana-graphite v6.4.4 container](https://github.com/dokku/docker-grafana-graphite/tree/6.4.4)
currently in use by dokku-graphite is dated Nov 2019, and is based on a Python2(!)
version 0.9.x of graphite, and is hosted on Ubuntu 14.04(!!!), but more recent versions
of the container exist

### Tree of docker-grafana-graphite images

* [kamon-io](https://github.com/kamon-io/docker-grafana-graphite) Aug 2019 / graphite master (py3 enabled??), Grafana 5.2.2, alpine Linux
  + [jlachowski](https://github.com/jlachowski/docker-grafana-graphite) December 2015
    * [dokku](https://github.com/dokku/docker-grafana-graphite)
      - tag 6.4.4 *(YOU ARE HERE)* (November 2019) graphite 0.9.x, grafana 2.1.3, Ubuntu 14.04
       + master branch: (Aug 2022) graphite master (py3 enabled?), grafana 8.1.3, Ubuntu 20.04
  + [lachesis](https://github.com/lachesis/docker-grafana-graphite) February 2022: *USES PYTHON3* graphite master, grafana 8.4.2, alpine Linux

### fetcher.stats interface module

I've made a fetcher.stats module that abstracts data collection to be
independent of protocol/software.  As the older version (0.9) of
Graphite in use has no notion of "tags" or "labels" for related event
counters (ie; different outcomes for a processing path), fetcher.stats
can explicitly structure the data to include labeling.

### layers of Graphite

Graphite is a popular (if dated) statistics collection, storage and visualization app,
which contains multiple components:

1. Ingest of stats: carbon
2. Storage of stats: whisper
3. Access to stats: graphite-web (a django app):
    * http queries can extract raw data
    * http queries can render graphs as image file by api (not used here)
    * provides UI w/ dashboards and saved graphs (not used here)

Graphite's data ingest software/protocol (carbon) wants ONLY
aggregated data (cannot deal with multiple sources for a single
datum), so statsd is a popular front end for it.

Grafana is a stand-alone statistics rendering system that can pull stats
from any number of sources that is used here as a front end to graphite.

## Statsd

[Statsd](https://www.etsy.com/codeascraft/measure-anything-measure-everything/)
was invented at Etsy for monitoring, and uses a push model, which is advantageous
in our situation (easy to aggregate counters from multiple worker processes).

### Statsd metric types

1.  Counter:  An integer value that only increases (an odometer); An event counter.
2.  Gauge:  A numeric value that can go up or down (gas gauge, thermometer, load average, disk space used, queue length).
3.  Timer: aggregate statistics of duration timings.

[statsd metric_types page](https://github.com/statsd/statsd/blob/master/docs/metric_types.md)
The fetcher.stats wrapper implements statistic labels/tags regardless
of whether the underlying version of statsd includes support by
suffixing labeled statistic with alphabetically sorted LABEL_VALUE
elements.

## Schema

I'm trying to follow the following rules in naming statistics (using
'.' as a separator in examples, since that's what statsd uses).

1. All statistics start with "mc"
2. Second element in name is "prod", "staging", or an (angwin) username.
3. Third element is name of (Dokku) app, ie; "rss-fetcher"
4. Fourth element is name of process (ie; "worker")
5. Counter names should be plural
6. See [Prometheus practices for metric names](https://prometheus.io/docs/practices/naming/#metric-names) for further thoughts.

All grafana visible stats paths begin with "stats", and then one of
"counters" or "gauges".

Statsd counters are suffixed with "count" (per 10s sampling period?) and "rate" (per second?).

An example of a grafana path to graph all rss-fetcher per-feed counters is:
`stats.counters.mc.staging.rss-fetcher.worker.feeds.*.count`

### Note on Labels

Labels/tags on a statistic means that every unique set of labels will
be stored as a new/different time series, so it's important to be
mindful of how many different values (cardinality) that given label
might have.  Two different labels, each with ten possible values
will result in 100 different time series.  That's a lot of colors
to display!
