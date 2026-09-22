# 000: Stock Price Cold Query Baseline

Date: 2026-09-22. Status: Initial assessment complete; no performance optimization applied.

## Objective and scope

Use the fixed query `SELECT * FROM '<stock_prices_url>' WHERE symbol = ?` with `AAPL`.
Preserve the architecture of remote Parquet on Hugging Face, HTTP, and local DuckDB, with
all results materialized as a DataFrame. This iteration establishes the benchmark and measures
the fixed SQL path under the current client configuration. It does not measure the additional
initialization and `spec.json` validation in a full `Ticker.price()` call.

## Data and environment

| Item | Value |
| --- | --- |
| Hugging Face dataset | defeatbeta/yahoo-finance-data |
| Pinned commit | a46d68650c1f90b7331608350dced8364047b3f7 |
| File | data/US/stock_prices.parquet |
| Query parameter | AAPL |
| OS | macOS 26.6.2, arm64 |
| CPU / memory | 10 physical cores, 10 logical cores / 24 GiB |
| Python / pandas | 3.14.6 / 3.0.3 |
| DuckDB | 1.5.3 |
| cache_httpfs / httpfs | e39e73c / 52afb42 |
| DuckDB threads / memory_limit | 4 / 19GB, matching the current client's default memory conversion |
| HTTP keep-alive | false, matching the current client default |
| Cache mode / block size | on_disk / 1 MiB |
| Network | DuckDB's effective http_proxy is http://127.0.0.1:8118 |

The raw report contains extension binary hashes, script hashes, and all effective HTTP and
cache settings. Matching version labels do not necessarily imply identical extension binaries;
check SHA-256 hashes when reproducing the results.

## Cold state and timing

Each trial starts a separate Python process with a unique empty cache directory and no
preread of the target Parquet file. The current client's in-process cache configuration is
preserved, allowing reuse within a single query. The trial's temporary directory is removed
afterward; existing user caches remain intact.

The primary measurement uses the host's monotonic clock, from just before the parent launches
the worker until the DataFrame is fully materialized. Process startup, initialization, and
query execution including materialization are also recorded separately. Result validation,
report writing, process exit, and cache cleanup are outside the timed interval. Dependency
checks and extension binary hashing run before the trials and are excluded from query timing.

Isolating local data caches does not establish cold OS code pages, DNS, proxy, or remote CDN
caches. Preflight checks may also warm dependency code pages. The benchmark does not flush the
global page cache, to avoid interfering with other tasks. The network path and uncontrolled
caches limit how these results should be interpreted.

## Reproduction

Run from the project root. See the [README](../README.md) for dependency and extension setup.

```bash
./.venv/bin/python benchmark/bench.py --symbol AAPL --runs 3 --tag baseline --revision a46d68650c1f90b7331608350dced8364047b3f7
```

The runner uses the same pinned commit by default. Each run has a unique report filename and
preserves the success or failure status of every trial. Any failure, empty result, or result
inconsistency prevents the run from producing a comparison median.

## Measurements

[Raw report for the successful run](../results/runs/20260922T065915.037912Z_baseline_fe24771a.md)

| Trial | Process startup (s) | Initialization (s) | Query and materialization (s) | End to end (s) |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.017119 | 0.186228 | 15.676606 | 15.879953 |
| 2 | 0.025620 | 0.237117 | 13.918603 | 14.181340 |
| 3 | 0.025354 | 0.235898 | 19.176382 | 19.437634 |

| Statistic | Seconds |
| --- | ---: |
| Median | 15.879953 |
| Min | 14.181340 |
| Max | 19.437634 |
| Sample standard deviation | 2.682381 |

All three workers had distinct PIDs and separate cache directories that were empty before
query execution. Each returned 8,004 rows with identical schemas and row-multiset SHA-256:
`947f24337467c764459d3f78f296dfc4791cea1e3aeab68197a0e9d13a3662a1`.
The checksum ignores scan order while preserving duplicate rows.

After each query, disk cache files totaled 2,775,421 bytes. This is file size, not network
transfer volume. Combined worker user and system CPU time was approximately 0.47–0.48 seconds,
well below the 14–19 seconds of wall time. This suggests that waiting may dominate, but does
not distinguish network round trips, proxy behavior, remote service latency, or local blocking.
HTTP request counts, actual transfer volume, and per-request latency were not measured, so
these results do not establish a root cause.

The [sandbox network failure report](../results/runs/20260922T065748.379525Z_baseline_e9560a79.md)
preserves the first three attempts, which failed to establish remote HTTP HEAD connections.
That run is marked `invalid` and excluded from the successful baseline. The successful results
above were obtained after approval to run outside the sandbox.

## Optimization conclusion

No performance optimization was applied, so an improvement percentage is not applicable.
These measurements establish the starting point for subsequent comparisons. With only three
samples and substantial variation, future comparisons should use at least 10 trials and
alternate baseline and optimized configurations. Change one factor at a time while keeping
the data commit, symbol, result checksum, dependencies, and network path comparable.

First diagnose HTTP request behavior and waiting time, then test individual hypotheses such
as connection reuse. Keep diagnostic runs separate from official timing to avoid contaminating
the primary metric with sampling and logging overhead. See the
[DuckDB extension documentation](https://duckdb.org/community_extensions/extensions/cache_httpfs)
for the cache wrapper and its settings.

## Validation and edge cases

Seven local checks passed after implementation, using temporary Parquet files and separate
workers without depending on remote data:

| Edge case | Test and expected behavior |
| --- | --- |
| Symbol parameter safety / no match | Ordinary symbols, a single quote, SQL-injection-shaped text, and a missing symbol return only exact matches |
| Invalid inputs | Empty or whitespace-only symbols, control characters, and a mutable revision are rejected |
| Scan order and duplicate rows | Reversing rows preserves the checksum; removing duplicates changes it |
| Statistics and inconsistent results | Known samples produce the correct median; no successful samples produce no statistics; one sample has no standard deviation; differing results are marked inconsistent |
| Nonempty cache directory | The worker rejects reuse before querying |
| Timeout and process failure | Simulated slow and crashing workers produce timeout/error records |
| Complete worker execution | Local fixtures run with two independent cache directories, return correct results, and have timing segments that sum to end-to-end latency |

Three real remote queries and the CLI help check also completed. Actual sandbox connection
failures exercised network-error reporting. The benchmark does not guarantee a cold machine
and does not estimate p95/p99 from three samples.
