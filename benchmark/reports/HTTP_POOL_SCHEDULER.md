# Bounded connection expansion and scheduler review

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

The subsequent [cache pipeline timing report](CACHE_PIPELINE.md) adds detailed
task/bridge/lock attribution without changing this product implementation.
Its dataset differs, so it is not a direct performance comparison with this stage.

## Outcome

The allocator now expands an origin/route with bounded parallel initialization
after learning protocol capacity. Waiting request threads no longer repeatedly
dispatch the entire queue. Uncontended requests reuse ready capacity directly.
The existing HTTP/TLS stack, process connection budget, cache behavior, and
absence of periodic network keepalive remain unchanged.

Local correctness checks passed. The final in-car observations show substantially
lower uncached burst latency and process CPU time than the preceding manager.
They do **not** establish a general performance win: cached 128-query batches
were slower, including batches whose aggregate pool acquisition time was about
two milliseconds. Acceptance of an across-workload performance improvement
remains open. These measurements are not a comparison against release 0.0.62.

## Implementation and defaults

| Setting | Default |
| --- | ---: |
| `core_connections_per_origin` | 4 |
| `max_connections_for_all_origins` | 16 |
| `max_streams_per_connection` | 4 |
| `max_connecting_per_origin` | 4 |
| `extra_connection_idle_timeout` | 60 seconds |
| `Configuration.cache_fetch_workers` | 16 |

`max_connecting_per_origin` is the new exposed setting. Like the core target,
its grouping includes origin and transport route. Existing defaults were not
raised. Applications do not need to supply a configuration.

The first connection initializes alone. Once an established connection reveals
capacity, up to four connections in the group may initialize concurrently.
Expansion subtracts the estimated remaining capacity of connecting sockets
from queued demand, avoiding extra connections for small bursts. This estimate
only sizes expansion: a connecting socket still admits its first request alone,
and actual reservations obey that connection's negotiated limit and client cap.

A single allocator worker dispatches the ordered queue and signals individual
request events. A request with no earlier queued work and an eligible ready
slot reserves it directly under the allocation lock. Slow idle close operations
run outside the scheduler; closing sockets still consume the physical budget.
Status adds `dispatches` and `close_errors` to support diagnosis.

Core size is a retention target after demand creates connections, not forced
preconnection or guaranteed server-side retention. Sixteen fully ready HTTP/2
connections with four slots each permit at most 64 simultaneous reservations.
That is neither a Ticker concurrency limit nor a guarantee of optimal bandwidth.
Cached data fetches ordinarily encounter the shared sixteen-worker filesystem
executor before they reach HTTP admission.

## Review findings and regression coverage

Each confirmed failure below received a reproducing test before its fix.
Additional tests cover bounded expansion, small bursts, FIFO admission, and
route closure waking queued callers.

| Finding | Change | Regression coverage |
| --- | --- | --- |
| One connecting socket serialized all later initialization in its group. | Allow demand-sized parallel initialization after capacity discovery. | Known-capacity expansion, initialization cap, and no overbuilding. |
| Awakened request threads repeatedly scanned the full pending queue. | Centralize dispatch and signal assigned requests individually. | Waiters never execute full queue dispatch. |
| A ready, uncontended request could depend on a scheduler wakeup. | Reserve immediately when no earlier work is queued. | Ready-slot acquisition without worker notification. |
| Cancellation could race assignment between checking and removing a pending request. | Remove and inspect the abandoned assignment under the same lock; then release it. | Deterministic cancellation/assignment race leaves no reservation. |
| A slow idle close could stall scheduling for another ready origin. | Close asynchronously while retaining its budget. | Blocked close does not block a ready origin. |
| A close exception could strand later connections in a batch. | Attempt all closes, count failures, and propagate the first error. | Batch close failure leaves no stranded connection. |
| Resource eviction failure leaked a new borrower's active count; shutdown could omit later clients. | Protect borrower release with `finally` and attempt every client close. | Eviction failure releases borrowing; shutdown attempts all clients. |
| Socket-option failure called synchronous `close()` on an asynchronous stream. | Apply options on the protocol thread, await `aclose()`, and preserve the original error. | Option failure closes the stream and retains its exception. |
| Fork could inherit an allocator lock held by a vanished thread. | Replace the child process's global allocator and registry, preserving configuration. | Fork with the inherited lock held can use the child allocator. |

Fork coverage is limited to the HTTP allocator. Existing Ticker, DuckDB, and
CacheFS instances are not thereby safe to reuse across fork. The change does
not close inherited protocol objects through the parent's live runtime.

Existing tests also cover dynamic SETTINGS reduction, GOAWAY, pool deadlines,
failed initialization, streamed-response ownership, cross-origin/proxy budget
accounting, idle shrink, and footer/index single-flight sharing. No periodic
HTTP requests or HTTP/2 PING were introduced.

## Final-source network evidence

All runs below use the user-confirmed in-car network on October 11, 2026.
Existing proxy and TLS settings were preserved. No other validation workload
ran during the final network runs. Two rounds reverse candidate order;
consecutive batches reuse connections created by prior demand.

- Baseline: `results/local/20261011_in_car_http_pool_mixed_reuse.json`.
  This is the earlier refactored manager, not published release 0.0.62.
- Final 128-query run:
  `results/local/20261011_in_car_http_pool_scheduler_final.json`.
  Eight batches, 1,024 successful queries.
- Final low-concurrency run:
  `results/local/20261011_in_car_http_pool_scheduler_low_concurrency.json`.
  Eight batches, 36 successful queries.
- `results/local/20261011_in_car_http_pool_scheduler.json` records an intermediate
  implementation and is not the final-source result used below.

The dataset version is `2026-10-10T05:08:13Z`. Every final batch has zero query
failures, cached fallbacks, preparation errors, and connection-close errors.
Observed Range body bytes equal reported downloaded bytes. All overlapping
symbol/API fingerprints match the baseline (128 distinct pairs overall).
Both final reports match all seven recorded product-module hashes and all
three diagnostic-module hashes at validation time.

Each 128-query batch uses 32 symbols and four APIs: `price`, `info`, `calendar`,
and `dividends`. It does not represent 128 independent Ticker owners. Cached
batches prepare footer/index metadata and clear data extents before measurement;
uncached batches use `cache_enabled=False`, may repeat footer reads, and do not
perform symbol prefetch. Compare changes within each path, not their absolute
throughput. See [the original method](HTTP_POOL_MIXED.md).

Global budget 16, query P95 in seconds; pairs denote rounds 1 / 2:

| Path and batch | Baseline P95 | Final P95 | Baseline process CPU seconds | Final process CPU seconds |
| --- | --- | --- | --- | --- |
| Cached, first | 4.573 / 4.646 | 4.839 / 6.290 | 4.309 / 6.904 | 5.439 / 7.128 |
| Cached, repeat | 2.226 / 2.681 | 4.754 / 5.153 | 3.767 / 4.852 | 6.506 / 6.553 |
| Uncached, first | 33.924 / 33.720 | 9.821 / 8.594 | 41.192 / 42.636 | 12.657 / 11.504 |
| Uncached, repeat | 18.557 / 19.211 | 8.494 / 6.863 | 21.601 / 23.900 | 10.540 / 8.525 |

Uncached first-batch P95 is about 71-75% lower; repeat P95 is about 54-64%
lower. These are observed before/after differences, not an isolated causal
estimate. Baseline and final runs were not interleaved, and mobile network
conditions can change within a session. Process CPU includes the whole benchmark,
not only allocator work; it cannot quantify the scheduler's individual saving.

Final accounting (pairs again denote rounds 1 / 2):

| Path and batch | Batch wall seconds | Accumulated pool wait seconds | Accumulated worker queue seconds | Dispatches |
| --- | --- | --- | --- | --- |
| Cached, first | 6.106 / 8.111 | 7.030 / 7.411 | 73.406 / 95.646 | 139 / 138 |
| Cached, repeat | 5.711 / 5.659 | 0.0016 / 0.0017 | 79.648 / 79.343 | 110 / 111 |
| Uncached, first | 11.294 / 9.998 | 391.157 / 359.152 | 0 / 0 | 889 / 894 |
| Uncached, repeat | 9.430 / 7.865 | 166.776 / 159.022 | 0 / 0 | 668 / 657 |

Pool and worker totals sum overlapping request/task spans. They must not be
read as batch wall time, an individual query's delay, or additive time phases.
The larger cached worker queue identifies where requests wait; it does not
establish why workers finish more slowly. Slower network/body delivery or local
processing can also increase that queue. The cached regression remains unresolved.

Final cached batches use four CDN connections and sixteen peak reservations.
Round one also retains an idle metadata connection, for five total sockets.
Uncached bursts reach the global limit of sixteen and 64 reservations in the
first batch. Repeat batches create no new connections. Concurrent snapshots
confirm full-budget, fully reserved uncached connections with queued work.
The observed CDN peer limit is 100 and the effective per-connection client
limit is four. This is not an inventory of every possible dataset origin.

Every cached batch downloads 49,939,908 bytes and every uncached batch downloads
139,517,355 bytes, matching the respective baseline workloads. Final application
throughput spans 6.157-8.824 MB/s cached and 12.353-17.738 MB/s uncached. These
values include prefetch drain in elapsed time and do not prove physical-link
saturation. Raising the global budget is not justified by this comparison.

## Low-concurrency check

With connection and metadata preparation complete but data extents cleared,
four single-query `PDD.price()` observations take 0.664, 0.541, 0.529, and 0.538
seconds. All reuse existing connections without opening new ones. This is a
current observation, not a controlled improvement over an earlier network.

For eight mixed queries, first-batch P95 is 1.720 / 2.310 seconds and repeat
P95 is 1.491 / 1.032 seconds. Each first batch opens one additional connection;
each repeat opens none and has no sampled pending pool requests. Second-round
ordering runs eight queries before one query, so the latter reuses an expanded
pool. There are too few samples to claim a stable latency distribution.

## Validation and remaining scope

The final product implementation passed 319 local tests with one skipped:

```sh
.venv/bin/python -m unittest \
  test.test_dataset_cache_fs test.test_resolve_direct test.test_benchmark \
  test.test_duckdb_client.TestDuckDBClient test.test_test_collection \
  test.test_shared_resources test.test_http_pool test.test_http_runtime \
  test.test_shared_query_benchmark test.test_connection_timeline \
  test.test_http_pool_mixed -q
```

These are macOS local results. Workflow coverage now includes the timeline and
mixed diagnostics, but remote CI and other operating systems were not run in
this validation. Whitespace and added-Chinese-character checks passed.

Remaining review items are deliberately distinguished from confirmed bugs:

- The synchronous response facade still crosses into the I/O loop for each
  yielded body chunk. Its overhead and buffering tradeoffs are not measured.
- The shared sixteen-worker data executor remains an upstream admission limit.
  Raising it without understanding delivery and processing costs is unsupported.
- Cache extent lookup scans the directory; large-cache scaling is a source-level
  concern, not an established bottleneck in these runs.
- First client initialization holds the shared client registry lock across
  network setup, serializing different configurations as well as matching ones.
  Matching-configuration single-flight is intentional; unrelated initialization
  contention remains unmeasured.
- Before claiming general performance improvement, separate cached worker service
  time into network/body delivery and local processing, and isolate scheduler
  overhead with a controlled local workload. Repeating mobile measurements until
  a favorable result appears would not resolve the cached regression.

The implementation fixes demonstrated allocation and lifecycle defects. It does
not select a universal throughput-optimal pool size or establish that bandwidth
is the remaining performance limit.
