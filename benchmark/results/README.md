# Benchmark records and reports

## Local iteration and publication

The benchmark uses an explicit two-stage workflow:

1. Run `benchmark.py run` as many times as needed while developing an optimization.
   Each invocation writes one ignored JSON record under `local/`; it does not
   create a Markdown report or a tracked archive.
2. After selecting satisfactory baseline and candidate runs, invoke
   `benchmark.py archive` explicitly. Archiving validates and combines those exact
   records into one tracked comparison JSON and one Markdown report without
   rerunning the benchmark.

Local execution is unlimited, while storage is intentionally bounded: the
newest 100 records from the last 30 days are retained. Use
`--baseline-source` and `--candidate-source` to select the exact runs that
should become durable evidence. Archives are created exclusively and are never
silently replaced.

## Storage layout

- `local/<run-id>.json`: one file per invocation, ignored by Git. Completed runs retain the newest 100 within 30 days. Cleanup runs after each benchmark; recent unfinished runs are protected, and unfinished records older than 30 days expire.
- `archive/NNN_<name>.json`: one immutable paired baseline/candidate record for a published optimization.
- `archive/NNN_<name>.md`: the single generated comparison report for that optimization.

Run from the project root (one file per invocation, unlimited runs):

```bash
./.venv/bin/python benchmark/benchmark.py run \
  --runs 3 \
  --tag <attempt-tag> \
  --http-proxy http://127.0.0.1:8118
```

Publish one satisfying comparison from the project root (archiving does not run queries):

```bash
./.venv/bin/python benchmark/benchmark.py archive \
  --baseline-source benchmark/results/local/<baseline-run-id>.json \
  --candidate-source benchmark/results/local/<candidate-run-id>.json \
  --name 001_connection_reuse
```

If the candidate intentionally changes a configured setting, declare each one
with `--allow-setting-difference <name>`. Undeclared differences, mismatched
environments, revisions, symbols, or result hashes reject publication.

The executable benchmark calls `Ticker(symbol).price()` through the real
`defeatbeta_api` package. Its primary metric is the time emitted by
`DuckDBClient._execute_query`; package import, client initialization, the full
API call, cache state, DuckDB-requested byte ranges, network range transfers,
and DefeatBeta cache metrics are recorded separately.

`--cache-layout extent` is the production default. It stores variable-length
reader ranges and downloads only uncovered intervals. The first query for a
Parquet file prepares that file's footer and, for a simple symbol scan, its
row-group index. Both are versioned and reused by later queries for the same
file, including queries for other symbols. No file footer is fetched during
client initialization. The initial preparation is included in
`_execute_query`. `metadata_prepare_performance` and
`range_prefetch_performance` report metadata work and prefetch scheduling
separately.
`--cache-layout io` is a compatibility alias; `--cache-layout block` retains
the aligned-block reader for rollback and comparison. The cache snapshot is
verified empty before each measured cold API call. A four-byte Parquet header
extent is classified as metadata rather than query data in the separate
data-extent snapshot. `--no-cache-footer-preload` disables explicit footer
preparation for a control run, but does not prevent DuckDB from reading
required Parquet metadata itself.

Transport experiments can use `network-cold-read` to compare fresh independent
connections, disjoint connection warmups, and Range chunk sizes. It downloads
the same ordered query bytes for each mode and verifies their digest, but it is
network-only evidence, not an API performance result. Use `run` with
`--cache-network-connections`, `--cache-network-chunk-size`, and
`--cache-connection-warmup-bytes` for the end-to-end check. Connection warmup
occurs before `Ticker.price()` and is reported separately as
`connection_warmup_seconds`; its bytes are not stored in the local range cache.
The production client also performs a one-byte startup prewarm during client
initialization, so this optional benchmark warmup is additional. Its time is
included in client initialization, not in `_execute_query`. The connection
pool is shared by files with the same resolved origin; a different origin gets
its own lazily created pool. `cache_network_connections` applies per origin.
These command-line settings do not change
production defaults.
The proxy option is optional: omitting it uses the normal environment proxy
policy, while an explicit proxy selects that route for the run.

The `archive/000_*` and `archive/001_*` files are historical records from the
previous `cache_httpfs` reader. They are kept unchanged so past measurements
are not presented as measurements of the current reader.

Local run JSON uses format version 2 with deduplicated `shared` entries. Paired
comparison archives use format version 3 and embed the exact version 2 baseline
and candidate records. `000_baseline` and `001_resolve_once_cdn` are legacy
archives produced by the retired direct-DuckDB benchmark and remain readable
by `report.py`.
