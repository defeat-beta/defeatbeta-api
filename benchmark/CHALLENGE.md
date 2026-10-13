# DefeatBeta Performance Challenge

> **How fast can a serverless data lake become?**

## Background

Data lakes are powerful — but they are also intimidating.

If you have ever tried to build one, you probably know the drill:

**S3 → Hive Metastore → Spark → Presto/Trino → Data Catalog → IAM → ...**

Before the first dataset is even queryable, you are already deep inside infrastructure.

But what if you do not need all of that?

What if you are a researcher, an independent developer, or simply a data enthusiast who wants a **simple, free, and maintenance-free way to store and query large datasets**?

This is the idea behind what I call a:

> **Poor Man's Data Lake**

DefeatBeta API is built around this idea.

Its architecture is intentionally simple:

```text
Hugging Face
    │
    │  Parquet over HTTP
    ▼
  DuckDB
    │
    ▼
Application
```

The data is hosted on Hugging Face, the query engine runs locally, and Parquet files are queried directly over HTTP.

There is:

* no database server
* no Spark cluster
* no data warehouse
* no always-on infrastructure to maintain
* almost no hosting cost

Just:

> **Files + HTTP + a query engine**

Simple. Cheap. Serverless.

But simplicity comes with a price:

> **The network is now part of the query engine.**

Remote reads, HTTP latency, metadata access, Parquet layout, data transfer, caching, query planning, and execution can all become bottlenecks.

That leads to the question behind this project:

> **How far can we push this architecture before we hit its fundamental performance limit?**

---

## The Challenge

Use **Systems Engineering + First Principles Thinking** to push DefeatBeta's query performance as far as possible.

For now, the primary benchmark is:

> **Cold Query Latency**

The goal is to minimize the time from starting a real query until its result
is fully materialized, when the required data is not already cached locally.

Each published benchmark result must document its preparation, cache state,
and timing boundary so that the result can be reproduced and interpreted
correctly.

The current production reader is DefeatBeta's demand-driven extent cache. A
fresh worker gets an isolated empty cache directory for each cold sample;
optional warm repeats reuse that directory and connection. The benchmark
records downloaded bytes, Range GET events, cache hits and misses, and the
time spent inside `DuckDBClient._execute_query`. A signed CDN URL is not part
of the persistent cache key.

The first query for a Parquet file prepares its versioned footer on demand.
With column prefetch enabled, a simple symbol scan also builds a reusable
in-memory row-group index from the cached footer. Queries for other symbols
in that file reuse the parsed metadata.
This preparation is inside the measured query, not client
initialization. `--no-cache-prepare-footer-on-first-use` disables explicit footer preparation
for a control run; DuckDB still reads the metadata it needs. The project cache
has one demand-driven extent layout; there is no layout selection flag.
`--no-cache-symbol-column-chunk-prefetch` isolates the effect of column-chunk prefetch
without disabling footer preparation or the demand-driven local cache. The
benchmark can select another supported Ticker DataFrame API with
`--api-method` to check more than the stock price file.

To measure repeated local data-cache misses after the file footer is already
cached, use a symbol sequence in one worker and cache directory:

```sh
python benchmark/benchmark.py sequence --symbols AAPL,KDP,ZTS,KDP --runs 3
```

Each trial starts with an empty cache. The first symbol downloads the footer;
later symbols must either download new data ranges or reuse existing data.
The final repeated symbol is a hot-data control. The record captures Range
events, downloaded bytes, and `_execute_query` time for every step, and marks
overlapping re-downloads or a second footer download as invalid. Sequence
records remain local diagnostics and are not automatically published. Use
`--http-proxy` only when your network requires one.
`--cache-fetch-workers` controls concurrent extent-fetch tasks, and
`--cache-range-split-bytes` supports controlled single-Range versus
split-Range comparisons. One pooled HTTP client per origin can issue
concurrent requests; increasing the worker count does not imply a
universally faster result.

To isolate network transfer phases on the same Parquet revision, use its
locally cached `.footer` extent:

```sh
python benchmark/benchmark.py network-rowgroup \
  --footer /path/to/stock_prices.parquet-START-LENGTH.footer \
  --runs 3 --output /tmp/rowgroup-probe.json
```

Add `--http-proxy URL` only where a proxy is required. DuckDB derives the
row-group metadata from the cached footer; the probe verifies the remote
footer digest against those local bytes before measuring. Each sample
uses a different complete row-group byte span of comparable size; trial order
rotates single, two-part, and three-part Range GETs. Each transfer records
time to headers, time from headers to first body bytes, and body transfer
time. These are network-only diagnostics, not end-to-end API results. A proxy
or CDN may cache at an unknown granularity, so compare multiple trials and
the separate `sequence` results before changing production defaults.
For a second crossover, change `--mode-offset` to `1` or `2` and use a
`--group-offset` that fits within each selected row-group interval (for
example, `1`). This changes both the first measured mode and the chosen
row groups, reducing startup-order and repeated-range bias.

For byte-level diagnosis, run one sample with `--trace-io`, then classify its
saved read and Range events against the exact same Parquet revision downloaded
locally:

```sh
python benchmark/benchmark.py inspect-io \
  --record /path/to/local-run.json \
  --parquet /path/to/stock_prices.parquet \
  --expected-sha256 EXPECTED_LFS_SHA256 \
  --pages
```

`inspect-io` is offline and read-only. It attributes bytes to the footer,
header, row-group column chunks, or unmapped gaps. A matching checksum is
essential because the remote dataset is updated regularly.
`--pages` additionally parses physical page headers in chunks touched by the
trace. It reports page byte offsets and row-value counts without assuming that
DuckDB reads or HTTP Range requests align with page boundaries.

Explore aggressively. Measure everything. Question every implementation detail.

But there is one fundamental constraint.

---

## Principles

### Do not change the architecture

This is the most important rule.

The architecture must remain:

```text
Remote Parquet on Hugging Face
            +
         HTTP
            +
      Local DuckDB
```

The goal is **not** to make the benchmark fast by turning DefeatBeta into another architecture.

Do not solve the problem by introducing:

* a traditional database server
* a data warehouse
* a Spark/Trino cluster
* a persistent query service
* a separately operated backend
* a full local copy of the dataset

The challenge is to discover how fast the **existing serverless architecture itself** can become.

Everything inside that boundary is open to optimization.

Parquet layout, HTTP behavior, range requests, metadata access, concurrency, caching strategies, prefetching, DuckDB configuration, query planning, indexes, execution strategies, and implementation details can all be challenged.

### Measure, don't guess

Every optimization should be validated by reproducible benchmark results.

The question is not whether an idea sounds faster.

The question is:

> **Did it make the cold query faster?**

### Optimize end to end

Microbenchmarks are useful for understanding bottlenecks, but the final metric is end-to-end query latency.

An optimization only matters if it improves the actual query.

---

The architecture stays.

Everything else is fair game.

**Let's find its limit.**

---
