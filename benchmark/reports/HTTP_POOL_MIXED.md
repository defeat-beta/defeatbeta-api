# Mixed API connection-budget validation

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

This report describes the validation stage before the
[bounded-expansion implementation and scheduler review](HTTP_POOL_SCHEDULER.md).
Its source observations and proposed next steps refer to that earlier manager.

## Decision

Do not raise the default global connection budget based on these measurements.
The default cached path did not exhaust its 64 potential HTTP/2 reservations
at 128 simultaneous mixed queries. The uncached path did exhaust them, but a
larger budget did not produce a repeatable latency or throughput improvement.
Burst expansion must be evaluated separately from steady connection capacity.
Product code and defaults were not changed by this validation.

## Network and evidence

The user switched to an in-car network on October 11, 2026. Both result sets
below were started after that notification. They are not home-network or
company-network comparisons.

- `results/local/20261011_in_car_http_pool_mixed.json`: two rounds of 32,
  64, and 128 simultaneous queries, four candidate policies, 24 batches,
  1,792 successful queries. Local timeline tests overlapped initial cached
  candidates; cached capacity comparisons use the later isolated report.
- `results/local/20261011_in_car_http_pool_mixed_reuse.json`: two rounds,
  128 simultaneous queries, two consecutive batches per candidate, 16 batches,
  2,048 successful queries. No other validation workload ran during this run.
- `results/local/20261011_home_http_pool_mixed_preflight.json`: execution
  preflight only. Its network became uncertain during a reported network
  transition, and it is explicitly excluded from capacity comparisons.

All 3,840 queries in the two in-car reports succeeded, with no cached fallback
or observed metadata/prefetch preparation error. All 128 distinct symbol/API
result fingerprints matched across budgets, paths, and rounds. Reported
downloaded-byte metrics matched observed Range response body bytes for every
batch. Product source hashes matched the seven recorded client modules at that
validation stage. The reuse report also matched its diagnostic source hashes.
The observed dataset version was `2026-10-10T05:08:13Z` for every candidate.

## Method

Each of 32 symbols calls four APIs:

| API | File |
| --- | --- |
| `price` | `stock_prices.parquet` |
| `info` | `stock_profile.parquet` |
| `calendar` | `stock_earning_calendar.parquet` |
| `dividends` | `stock_dividend_events.parquet` |

The 32/64/128-query workloads contain 8/16/32 symbols respectively, each with
all four APIs. They use one shared Ticker client and filesystem owner. This is
query concurrency, not 128 distinct Tickers or an HTTP stream count.

Only `max_connections_for_all_origins` changes between budgets 16 and 32.
Core retention remains four per origin/route, the scheduling ceiling remains
four streams per connection, download workers remain sixteen, and surplus
idle timeout remains sixty seconds. Proxy and TLS settings are preserved.
The observed data origin was `us.aws.cdn.hf.co`, advertising 100 streams per
connection; the effective client limit was four. This does not enumerate all
remote dataset objects or guarantee the same setting on another origin.

Candidates and their batches run sequentially. Candidate and concurrency
order are reversed in the second round. Every candidate starts with a fresh
pool and four sequential API warmups. No synthetic preconnections are forced.
The cached path prepares all four footer/index objects, then clears only data
blocks before each measured batch. The uncached path uses public
`cache_enabled=False`; it can repeat footer reads and lacks cached symbol
prefetch. The two paths are not equivalent byte workloads and are compared
within each path. DuckDB external file cache is disabled; its default metadata
cache and four query threads remain unchanged.

In the reuse report, batch two repeats the same 128-query workload immediately
after batch one and reuses demand-created connections. It may still create
additional connections, so it is not an artificially fully expanded pool.
Fingerprints are computed outside query timing. Downloaded-byte throughput
includes prefetch drain and is application throughput, not wire bandwidth.

## Consecutive-batch results

Second-batch results for 128 simultaneous mixed queries:

| Path | Global budget | Peak CDN connections, rounds 1 / 2 | Peak reservations, rounds 1 / 2 | Query P95 seconds, rounds 1 / 2 | Application MB/s, rounds 1 / 2 |
| --- | ---: | --- | --- | --- | --- |
| Cached | 16 | 4 / 4 | 16 / 16 | 2.226 / 2.681 | 14.326 / 11.429 |
| Cached | 32 | 4 / 4 | 16 / 16 | 2.408 / 3.540 | 14.458 / 10.357 |
| Uncached | 16 | 16 / 16 | 64 / 64 | 18.557 / 19.211 | 7.265 / 6.668 |
| Uncached | 32 | 18 / 18 | 71 / 69 | 27.230 / 17.018 | 4.732 / 7.843 |

Each batch has 128 query samples. P95 is empirical nearest rank; queries in
one batch share network and scheduling conditions. An idle Hugging Face
metadata connection remained in the first cached candidate, making its total
physical connection peak five while its CDN connection peak stayed four.

Every cached 128-query batch downloaded 49,939,908 bytes. Every uncached
128-query batch downloaded 139,517,355 bytes. This byte difference is part of
the cache/prefetch/coalescing behavior, not a connection-budget effect.

The cached second batches have no sampled pool pending requests and only
0.0023-0.0041 seconds of accumulated pool acquisition time. Their accumulated
download-worker queue time is 34.0-50.7 seconds across tasks. These sums overlap
and must not be interpreted as a query or batch wall duration.

The uncached budget-16 second batches contain snapshots of sixteen ready CDN
connections, all 64 reservations occupied, and 53 or 42 pending requests in
the same snapshot. This is direct evidence of capacity exhaustion, rather than
combining separate connection, reservation, and queue peaks.

The budget-32 second batches use eighteen connections, not thirty-two, and
never show the entire global budget saturated with a queue. The larger budget
performs worse in one round and better in the other. This is not evidence that
128 fully ready reservations are either optimal or useless.

## Why a queue can exist below the connection budget

Source inspection explains two independent admission limits:

1. `get_duckdb_client()` shares a client for matching configuration, proxy,
   and logging settings. Its single `DatasetCacheFileSystem` submits data
   extent fetches for all files to one sixteen-worker executor. With metadata
   ready and range splitting disabled, ordinary data downloads are therefore
   limited before reaching the process HTTP pool. Metadata, uncached fallback,
   independently configured owners, or explicit range splitting can use other
   paths; sixteen is not an unconditional process-wide HTTP request limit.
2. `ConnectionManager._dispatch()` requires `not connecting` before creating
   another connection in an origin/route group. A connecting connection admits
   only its first request until protocol readiness is known. Consequently,
   connections initialize sequentially within that group even when the global
   budget has space and waiting requests could use additional ready capacity.

In all four uncached first batches, the pool starts with one connection and
grows to thirteen. P95 is 33.7-38.2 seconds. Every sampled pending observation
is below the connection budget; all but one in each batch coincide with a
connecting connection. The same pattern also appears during cached expansion
from one connection toward four. Raising the global maximum does not remove
this initialization coordination rule.

The allocator also wakes waiters with `notify_all()`, and each awakened
`acquire()` may scan the pending list and connection groups under one condition
lock. Protocol readiness callbacks need that lock on the I/O thread. This is
a source-level contention risk, not a measured attribution of the observed
delay. Likewise, the synchronous response facade crosses into the event loop
for each yielded body chunk. These local costs should be distinguished from
TCP/TLS establishment and remote response time before changing the scheduler.

## Limits and next engineering step

This validation establishes where admission queues occur; it does not select
a universal optimal connection count or prove bandwidth saturation. Network
conditions can vary within an in-car session. The cached budget comparison,
which does not reach either global budget, also shows timing variation. There
are only two rounds, instrumentation overhead is not subtracted, and five-ms
sampling can miss short-lived states. Queue observation counts are not wall
time fractions. In the reuse report, 197 of 2,664 Range requests lack query
context, so per-query observed HTTP overlap is incomplete. Batch-level byte and
pool accounting is still checked independently.

The next design discussion should address demand-driven expansion under a
burst: after protocol capacity is known, consider a bounded number of parallel
initializations while preserving reuse, FIFO admission, pool deadlines, and
the atomic global physical-connection budget. Separately verify allocator
lock contention and the body-chunk bridge before attributing delay to the
remote server. No new protocol stack or periodic network keepalive is needed.
Changes to product scheduling require a separate approved implementation plan.

## Diagnostic checks and edge cases

Eighteen diagnostic tests passed: seven mixed-benchmark checks, two shared-query
benchmark checks, and nine existing timeline checks. The new checks cover
balanced distinct tasks, reversed ordering with adjacent reuse batches,
simultaneous queue/capacity evidence, initialization below budget, overlapping
worker/pool spans, failed or empty observations, and changed result fingerprints.
`git diff --check` and the no-added-Chinese check passed.

Further acceptance cases for a scheduler change should cover:

- A cold burst with no peer settings yet, followed by a known low peer limit:
  bound parallel initialization and never reserve beyond actual ready capacity.
- A full global budget across multiple origins and owners: preserve FIFO,
  reclaim eligible idle capacity, and include connecting/draining/closing sockets.
- Dynamic SETTINGS reduction, GOAWAY, failed initialization, cancellation, and
  pool timeout: release reservations once and allow subsequent queued work.
- Shared overlapping extents across files and symbols: preserve single-flight
  downloads and distinguish worker admission from HTTP pool admission.
- Empty query results, data-version changes, and metadata fallback: detect
  mismatched results and exclude contaminated comparisons.

Reproduce the clean consecutive-batch validation with:

```sh
.venv/bin/python -m benchmark.workloads.http_pool_mixed \
  --output benchmark/results/local/NEW_UNIQUE_RESULT.json \
  --network-label 'Describe the current network' \
  --budgets 16 32 --concurrency 128 --batches-per-concurrency 2 --rounds 2
```
