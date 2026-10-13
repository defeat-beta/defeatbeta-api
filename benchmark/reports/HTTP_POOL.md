# Process-wide HTTP pool engineering

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

The later [mixed API capacity validation](HTTP_POOL_MIXED.md) compares global
budgets under cached and uncached concurrent queries on the in-car network.
It separates download-worker admission, connection initialization, and full
HTTP reservation capacity. The subsequent [scheduler review](HTTP_POOL_SCHEDULER.md)
documents bounded parallel initialization, lifecycle fixes, final-source checks,
and the unresolved cached-path latency regression. Existing defaults remain
unchanged; the new initialization limit defaults to four.
The [cache pipeline report](CACHE_PIPELINE.md) records the follow-up timing
investigation, including HTTP/2 read coordination and diagnostic overhead.

## Result and scope

The download path now has one physical-connection allocator for the process.
Ticker owners, files, origins, proxy routes, and TLS trust configurations share
its connection budget. HTTPX/httpcore still implement HTTP, TLS, TCP, proxies,
flow control, and GOAWAY. No custom protocol or periodic keepalive is added.

Default policy:

| Setting | Default | Purpose |
| --- | ---: | --- |
| `core_connections_per_origin` | 4 | Retain up to four established connections per origin and route after demand expands the pool. |
| `max_connections_for_all_origins` | 16 | Bound all connecting, active, idle, draining, and closing physical connections together. |
| `max_streams_per_connection` | 4 | Client scheduling ceiling; also obey the peer and httpcore limits. |
| `extra_connection_idle_timeout` | 60 seconds | Reclaim surplus connections after continuous local idle time. |
| `Configuration.cache_fetch_workers` | 16 | Allow sixteen extent-fetch tasks per registered filesystem. |
| `max_connecting_per_origin` | 4 | Bound concurrent initializations after the first connection establishes protocol capacity. |

Applications can use these defaults without calling `configure_connection_pool`.
Configuration and status APIs are documented in
[Advanced Usage](../../doc/api/Advanced_Usage.md). Reconfiguration requires no
active or queued work. The core target is best effort under the global budget.
It is an idle-retention target, not a minimum number of preconnected sockets.

## Allocation and ownership

```text
Ticker / registered cached or uncached dataset filesystem
  -> SharedHttpClient
  -> transport selected by effective proxy and TLS trust configuration
  -> process ConnectionManager: origin group, deadline, atomic reservation
  -> synchronous facade / process HTTP I/O event loop
  -> existing async httpcore connection and AnyIO TLS/network backend
  -> operating-system TCP / existing proxy route / remote origin
```

New requests first reuse available core slots, balanced by reserved-slot ratio.
Surplus connections are eligible when core slots are unavailable. A connection
is created only when no existing slot is available and queued demand exceeds
the expected future capacity of already connecting sockets. The global budget
and per-origin initialization limit both apply. The first connection initializes
alone; after protocol capacity is known, up to four may initialize concurrently.
Initialization admits only its first request until protocol settings are known.
This avoids making a request establish a new connection merely to fill the core
target while another connection still has free slots.

Uncontended requests reserve ready slots immediately without a worker handoff.
One allocator worker dispatches the ordered queue and signals each assigned
request individually. Protocol callbacks update readiness and signal this
worker; waiting request threads do not rescan the queue. Slow idle close operations
run separately while retaining their physical budget. Batch close failures do
not prevent attempts to close remaining resources. The global allocator resets
its locks and connection registry in a forked child, preserving configuration.

Allocation reserves a slot atomically before protocol dispatch and keeps it
until response closure. Reservations include requests assigned before HEADERS
are sent and responses still being consumed. They are more conservative than
the current count of open wire streams. HTTP/1.1 has one slot per connection.
HTTP/2 capacity is the minimum of peer SETTINGS, httpcore's limit, and the
configured scheduling ceiling. The peer may advertise 100 or 128 streams;
the client default of four does not change that negotiation.

When all slots or the global connection budget are occupied, requests enter
the allocator's ordered queue. Pool waiting is bounded by the request's pool
deadline, including safe connection reassignments. Idle connections from other
groups may be retired to serve a new origin. Closing connections retain their
budget until closure finishes. The status API reports pending requests,
reservations, limits, connection counts, and accumulated allocation wait time.
It cannot infer remote service queues or remaining network bandwidth.

No timer sends an HTTP request or HTTP/2 PING. OS TCP keepalive is enabled on
direct and proxy sockets using OS timer defaults. It cannot keep an HTTP session
open against server policy. Real requests reuse eligible connections; GOAWAY or
an unusable idle connection is handled by the existing stack and bounded
reassignment on demand. Extra connections shrink locally. Core connections may
also be retired by the server or reclaimed for another group.

Footer and parsed-index sharing remains process-wide and single-flight by
validated file/version. Retained disk footers survive process restarts. Reading
a footer does not update its modification time. See
[the shared-resource report](SHARED_RESOURCES.md) for cache ownership tests.

## Protocol concurrency correction

Repeated verified-TLS tests exposed a synchronous-stack race during a legal
HTTP/2 SETTINGS reduction. An unmodified synchronous HTTPX control also failed
with a reduction from four to three streams. An isolated stream-semaphore
adapter reproduced it without the new allocator. Socket instrumentation found
a TLS EOF while the underlying TCP socket was not readable as closed; client
closure followed the failure. Separate instrumentation also exposed reversed
HTTP/2 stream IDs under concurrent synchronous dispatch.

The final implementation runs httpcore's existing async protocol and TLS stack
on one process event loop, keeping mutable protocol and SSL state on that
thread. The synchronous public API waits on futures; requests overlap while
network I/O awaits readiness. This follows the
[OpenSSL threading requirement](https://docs.openssl.org/master/man7/openssl-threads/)
that one SSL object must not be used simultaneously by multiple threads.
Trace callbacks remain synchronous and execute on the I/O thread; they should
return promptly. The facade rejects recursive blocking calls from that thread.

The outer allocator replaces httpcore's hidden stream semaphore with reserved
slots. This prevents a second admission queue and prevents a SETTINGS decrease
from blocking the protocol read lock while existing responses need to finish.
Existing streams may finish after a limit decreases; no new reservations exceed
the reduced effective limit. hyper-h2 still enforces the protocol limit and a
bodyless GET/HEAD rejected before transmission can be safely reassigned.

These private adapters are validated against `httpx==0.28.1` and
`httpcore[asyncio]==1.0.9`; both dependencies are pinned. Upgrading them requires
rerunning these protocol and proxy regressions, not simply widening bounds.

## Default selection and current-network evidence

Company-network exploration on October 10 compared core counts, filesystem
workers, and stream ceilings. It favored four retained connections, sixteen
fetch workers, and a four-stream scheduling ceiling for high-concurrency price
workloads. Those measurements precede the final protocol-thread and allocation
corrections and are historical evidence, not a final-source company baseline.
The failed Range exploration is retained and excluded from successful results.

The user switched to the home network on October 11. Final-source comparisons
there ran sequentially, with candidate and concurrency order reversed in round
two. Both policies used the same final manager, global budget of sixteen,
dataset version `2026-10-10T05:08:13Z`, and symbols. They prepared footer/index
metadata, cleared data extents before each batch, disabled DuckDB external file
cache, and included prefetch drain in downloaded-byte throughput. All query
fingerprints matched across policies. Existing proxy/TLS settings were preserved.

The conservative policy is core=2, workers=3, and no extra client stream ceiling.
It is not release 0.0.62 or the previous connection-pool implementation.

Two rounds, aggregated per-Ticker samples; seconds and decimal MB/s:

| Ticker concurrency | Conservative P50 / P95 | Default P50 / P95 | Conservative / default MB/s |
| ---: | ---: | ---: | ---: |
| 1 | 0.556 / 0.579 | 0.638 / 0.653 | 2.042 / 1.778 |
| 8 | 1.326 / 2.041 | 1.077 / 2.599 | 5.458 / 5.361 |
| 16 | 2.765 / 5.765 | 1.671 / 2.753 | 3.628 / 7.331 |
| 32 | 5.409 / 9.485 | 3.487 / 6.498 | 4.465 / 7.350 |

High-concurrency P95 improved by about 52% at sixteen Tickers and 31% at
thirty-two. This does not establish improvement at every concurrency: the
single-Ticker sample was slower, and eight-Ticker cold-start P95 still has an
expansion cost. At eight Tickers, the default's first batch P95 was 2.599 seconds
versus 2.041 for the conservative policy; after expansion, its second batch was
1.398 versus 1.885. These are individual batches, not independent estimates of a
universal cold/warm difference. An earlier four-round eight-Ticker retest exposed
unnecessary proactive core growth; a regression now forbids that behavior.
It reduced avoidable connection creation but cannot eliminate handshake cost
when all existing slots are occupied.

The final default reached four CDN connections and sixteen reserved requests
at higher price concurrency. Cold initialization briefly queued up to eleven
requests; established sixteen/thirty-two-Ticker batches observed no allocator
queue at the sampling instants. Sampling every 5 ms can miss short waits.
Sixteen filesystem tasks, four slots per connection, and four established
connections explain this workload's observed capacity. They do not make sixteen
the maximum number of concurrently executing Ticker queries.

The global maximum of sixteen is a bounded burst budget validated under real
loopback TLS oversubscription. The price workload used only four connections;
it does not prove sixteen is an internet throughput optimum. At sufficient
request demand, sixteen eligible HTTP/2 connections allow up to sixty-four
reserved requests under these defaults. A lower peer limit, HTTP/1.1, or mixed
routes reduces that capacity. Additional requests queue rather than creating
unbounded sockets. Cached queries can finish without reserving a network slot.

Raw reports are local, ignored artifacts under `benchmark/results/local/`:

- `20261011_home_http_pool_reuse_final.json`: final-source comparison above,
  sixteen completed batches, no failed queries, matching six client source hashes.
- `20261011_home_http_pool_defaults_final.json` and
  `20261011_home_http_pool_eight_repeat.json`: earlier home allocation and its
  repeatable cold-start downside; not pooled with final-source numbers.
- `20261010_http_pool_price_workers.json`,
  `20261010_http_pool_stream4_price.json`, and
  `20261010_http_pool_defaults_confirmation.json`: earlier company exploration.
- `20261010_http_pool_core_ranges.json`: failed company Range exploration;
  not used to claim an optimal core count.

Reproduce the final comparison on a named network:

```sh
python -m benchmark.workloads.http_pool_defaults \
  --output benchmark/results/local/http_pool_comparison.json \
  --network-label "Your current network" \
  --workload price --policies 2:3:peer 4:16:4 \
  --concurrency 1 8 16 32 --rounds 2
```

No test here establishes link saturation or a universal latency limit. P95 is
an empirical nearest-rank statistic; two batches provide correlated samples.
The benchmark measures application download bytes, not wire bandwidth. Defaults
favor directly usable high concurrency while retaining the documented cold-start
tradeoff; they are not settings users must change for different networks.

## Acceptance and edge cases

The final offline command ran 300 tests successfully with one optional live
smoke test skipped. Local verification does not claim the remote CI matrix has
run. CI includes the pool and runtime modules on Linux, macOS, and Windows.

```sh
python -m unittest test.test_dataset_cache_fs test.test_resolve_direct \
  test.test_benchmark test.test_duckdb_client.TestDuckDBClient \
  test.test_test_collection test.test_shared_resources test.test_http_pool \
  test.test_http_runtime test.test_shared_query_benchmark \
  test.test_connection_timeline -q
```

| Edge case | Regression / expected behavior |
| --- | --- |
| Existing slot available below core size | Reuse it; do not charge this request for unnecessary core growth. |
| 128 simultaneous real TLS Range reads across two paths | Sixteen connections, sixty-four reservations, sixty-four queued requests; all 128 finish correctly. |
| Concurrent connection initialization | One initializing connection per group; later callers observe negotiated capacity. |
| Global budget across direct/proxy/origin groups | Count every physical connection, including closure in progress. |
| Peer decreases SETTINGS below existing active count | Existing responses finish without deadlock; new admissions obey the lower limit. The TLS reduction test passed fifty repeated runs after the protocol correction. |
| Every idle core connection has received GOAWAY | Retire stale connections and establish a fresh one within bounded reassignment and the original deadline. |
| Unconsumed streaming response | Hold its reservation until closure; a waiting request can time out without leaking a queue entry. |
| Surplus connections become idle | Reclaim locally after the idle interval; never close active responses for shrinkage. |
| Factory failure or response-close failure | Remove pending ownership and retire unusable resources; later requests can recover. |
| HTTP CONNECT cold start | Coordinate creation and apply OS keepalive options to proxy sockets. |
| Protocol runtime exception / owner closure | Propagate the exception; later calls remain usable and other owners keep shared resources. |
| Managed async path in latency diagnostics | Preserve connection IDs, real socket-read spans, protocol timing, and close events. |
| Footer reuse, corruption, version change, concurrent processes | Single-flight validated preparation and retained disk reuse without rewriting footer mtime; reject stale or corrupt entries. |

Tracking: [issue 208](https://github.com/defeat-beta/defeatbeta-api/issues/208).
