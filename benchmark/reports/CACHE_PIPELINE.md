# Cache pipeline timing and attribution

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

The follow-up [ready-stream investigation](HTTP2_READY_STREAMS.md) confirms a
specific receive-coordination dependency with an uninstrumented controlled
reproduction and event-level real-query evidence. No product fix is included.

## Outcome and scope

This stage adds opt-in diagnostics and controlled tests. Product source files,
pool defaults, worker limits, and keepalive behavior are unchanged.

The final real-network capture places most **download-worker service time**
inside `_request_range`. Within the awaited HTTP operations, the largest
observed interval is waiting for the existing async HTTP/2 connection's read
lock. Socket reads are the next largest component. This is not evidence that
the lock is defective, that the pool lacks slots, or that all that time is
independent network delay.

The earlier cached-path regression is **not explained or fixed** by this stage.
The dataset changed, the network is variable, and detailed instrumentation has
measurable overhead. This capture identifies the current waiting mechanisms;
it is not an old/new product performance comparison.

## Diagnostic additions

`CacheTimeline`, in `benchmark/diagnostics/cache_timeline.py`, extends the existing timeline
only while its context is installed in an isolated diagnostic process:

- A task ID follows a submitted cache download through worker admission, Range
  requests, body consumption, cache publication, and completion. Shared query
  consumers are not all represented by the submitting query's ID.
- Each synchronous-to-async bridge records submission-to-operation-start,
  awaited-operation time, and operation-completion-to-caller-return. Their sum
  equals the observed call duration for completed operations. The middle interval
  includes protocol locks, I/O, event-loop scheduling, and processing.
- Per-filesystem wrappers distinguish generation-lock and guard acquisition
  from lock holding. Existing cache publication, atomic-write, extent-lookup,
  and pruning spans remain available. SHA-256 constructor work is timed while
  a download task is active; it includes both content and identifier hashes.
- Async HTTP/2 read, write, initialization, and state lock acquisitions are
  recorded separately from socket reads. The earlier base timeline's synchronous
  HTTPcore lock hooks did not observe the current asynchronous stack.
- Raw events, tasks, requests, query timestamps, and bridge records are retained.
  No signed URLs, proxy credentials, payload bytes, or exception text are stored.

The hooks are not product configuration. Existing diagnostics retain their old
behavior unless `--detailed-pipeline` is passed. Supplied filesystems must have
no outstanding work when hooks are installed or removed. Lock wrappers retain
the underlying synchronization objects and are restored on exit.

Raw detail is intentionally large: the real run has about 118,000 events per
batch, including roughly 46,000 guard acquisitions. These hooks perturb timing;
their output must not be presented as uninstrumented user latency.

## Controlled validation and instrumentation overhead

The TLS-verified local HTTP/2 fixture now supports deterministic Range payloads,
response-header delays, and delayed body chunks. Sending obeys the peer flow
control window and frame size. Its default one-byte behavior remains compatible
with existing GOAWAY, SETTINGS, and proxy tests.

Tests inject a blocked I/O loop, delayed response/body, and generation/read-lock
contention. They verify that the corresponding interval is observed, rather than
calling every delay a socket read. Concurrent downloads preserve task identity
through requests and writes. Exceptions, closed runtimes, cancellation before
dispatch, hook restoration, raw output, payload integrity, and output overwrite
protection are also covered.

The local comparison uses the same product with hooks disabled/enabled, reversing
order in round two. Each batch reads 32 disjoint 128-KiB ranges (4 MiB total),
with prepared connections and cleared data cache. The server runs in the same
process, so process CPU includes both client and peer. This is a cache-pipeline
workload, not a Ticker/DuckDB benchmark.

Final source, seconds; values are rounds 1 / 2:

| Download workers | Hooks-off batch wall | Hooks-on batch wall | Hooks-off query P95 | Hooks-on query P95 |
| ---: | --- | --- | --- | --- |
| 1 | 0.1172 / 0.1271 | 0.1446 / 0.1478 | 0.1114 / 0.1212 | 0.1374 / 0.1384 |
| 16 | 0.0913 / 0.3239 | 0.1398 / 0.1214 | 0.0871 / 0.0878 | 0.1103 / 0.1173 |

The final hooks-on query P95 is about 14-35% higher in these four pairs. The
hooks-off sixteen-worker second batch contains one 0.3208-second query and is
retained as an outlier, not rerun until favorable. Batch-wall overhead therefore
does not have a stable percentage. Do not subtract a fixed local percentage
from real-network observations. All eight batches succeeded with identical bytes.

## Final real-network capture

The network label uses the user's latest confirmation: in-car. No other test or
benchmark workload ran during capture. Existing proxy and trust settings were
preserved. The run uses default pool settings and sixteen cache download workers,
with 128 mixed queries over 32 symbols and four APIs, two consecutive batches
per round, and two rounds. Footer/index metadata is prepared; data blocks are
cleared before each batch. The first batch can expand the pool, and the second
reuses it.

The dataset is now `2026-10-11T04:59:20Z`, whereas the preceding scheduler
comparison used `2026-10-10T05:08:13Z`. Each current batch has **54 Range requests
and 47,480,151 downloaded bytes**, versus 58 requests and 49,939,908 bytes earlier.
Consequently, even byte workloads differ across those stages.

All 512 final queries succeeded, with no cached fallback, preparation error,
or connection-close error. All 128 distinct symbol/API fingerprints match
within this run. Every HTTP request has a download-task ID, downloaded bytes
match observed Range body bytes, and all recorded source hashes match the final
implementation and diagnostics at validation time. The peer advertises 100
streams; the effective per-connection ceiling is four. The cached workload
uses four CDN connections and sixteen peak reservations; round one also retains
an idle metadata connection. Neither repeat batch opens new connections.

Seconds; pool waiting is summed over requests, not batch wall time:

| Round / batch | Query P95 | Batch wall | Accumulated pool wait | Worker queue P95 |
| --- | ---: | ---: | ---: | ---: |
| 1 / first | 5.081 | 6.069 | 7.577 | 3.947 |
| 1 / repeat | 3.991 | 5.134 | 0.0014 | 3.052 |
| 2 / first | 4.585 | 5.262 | 7.970 | 3.310 |
| 2 / repeat | 4.016 | 5.067 | 0.0011 | 2.832 |

Repeat-batch cumulative components, in seconds:

| Observed component | Round 1 | Round 2 |
| --- | ---: | ---: |
| Worker service (`_fetch_block`) | 65.249 | 64.766 |
| Range operation (`_request_range`, nested in service) | 64.834 | 64.430 |
| Bridge submission to operation start | 1.377 | 0.945 |
| Bridge awaited operations | 62.539 | 62.712 |
| Bridge completion to calling-thread return | 0.842 | 0.707 |
| HTTP/2 read-lock acquisition (inside awaited operations) | 42.526 | 42.669 |
| Socket read (inside awaited operations) | 17.277 | 18.003 |
| HTTP/2 write-lock acquisition (inside awaited operations) | 1.955 | 1.424 |
| Generation-lock acquisition | 0.073 | 0.049 |
| Generation-lock holding, including publication | 0.306 | 0.262 |
| Atomic cache write (nested in holding) | 0.059 | 0.045 |
| Pruning (nested in holding) | 0.159 | 0.147 |

Worker service and Range time exclude time queued before worker execution.
Across all four batches, Range operations occupy about 98.7-99.5% of summed
worker service. This does not describe the entire query: query-side extent
lookup, waiting for shared futures, and DuckDB execution also matter.

For each bridge, protocol-lock and socket-read/write intervals were clipped to
its operation boundaries and merged before calculating uncovered time. They do
not overlap within the observed individual bridge calls. The unclassified
operation remainder is 0.530 / 0.361 cumulative seconds in repeat batches; it
includes protocol processing, instrumentation, and unobserved scheduling, not
pure CPU. Different bridges overlap, so these cumulative totals still cannot
be added to or compared as if they were exclusive batch-wall phases.

## Interpretation from the protocol implementation

In pinned httpcore 1.0.9, `AsyncHTTP2Connection._receive_events()` acquires
`_read_lock`, reads connection data when needed, and distributes the resulting
events to per-stream queues. Several stream coroutines can wait for that lock
while one coroutine reads the shared socket. A packet read for one coroutine
can contain data for multiple streams.

Thus 42 seconds of aggregate read-lock waiting does not mean one query waited
42 seconds, nor does it imply 42 seconds of removable lock overhead. Much of
it can overlap the socket read performed by another stream on that connection.
Socket read spans themselves include asynchronous resumption and TLS processing;
they are not packet arrival measurements or pure remote-service latency.

The repeated cached workload had available global budget and no material pool
admission delay. It is unsupported to increase the pool budget solely because
internal protocol read-lock waiting exists. Likewise, the worker queue grows
when earlier downloads take longer; its existence alone does not justify raising
the worker limit.

The generation-lock gap is real, but repeat-batch P95 is only 8.8 / 5.4 ms here.
It cannot on its own explain the preceding multi-second query differences.
Extent lookup remains worth examining: 398 calls per batch have P95 of roughly
63-128 ms and cumulative time of 10.7-18.1 seconds. That includes directory
inspection, cache lookups, synchronization, and instrumentation; it is neither
exclusive disk time nor proof of the earlier regression's cause.

Before a new product change, the remaining causal questions are whether slow
responses on shared connections delay otherwise-ready streams, and how much
query-side cache lookup costs without detailed hooks. Answering those requires
correlating connection/stream event timing and a controlled comparison, rather
than treating read-lock waiting as an automatic expansion signal.

## Artifacts and reproduction

Local ignored reports, preserved without overwriting:

- `results/local/20261011_loopback_cache_pipeline_final.json`: final local
  hooks-off/on comparison, eight batches and 256 successful range queries.
- `results/local/20261011_in_car_cache_pipeline_final.json`: final four-batch
  capture including asynchronous HTTP/2 lock waits, 512 successful queries.
- `results/local/20261011_loopback_cache_pipeline.json` and
  `results/local/20261011_in_car_cache_pipeline_detailed.json`: intermediate
  diagnostics before async lock timing; not final-source evidence.

```sh
.venv/bin/python -m benchmark.diagnostics.cache_pipeline \
  --output benchmark/results/local/NEW_UNIQUE_LOCAL.json \
  --workers 1 16 --tasks 32 --range-bytes 131072 --rounds 2

.venv/bin/python -m benchmark.workloads.http_pool_mixed \
  --output benchmark/results/local/NEW_UNIQUE_NETWORK.json \
  --network-label 'Describe the current network; detailed instrumentation' \
  --budgets 16 --concurrency 128 --cache-modes cached \
  --rounds 2 --batches-per-concurrency 2 --detailed-pipeline
```

Final local regression: 329 tests executed, one skipped, all others passed.
The ten new diagnostic tests are in `test/test_cache_timeline.py`; CI path and
test-list coverage includes them. Remote CI and other operating systems have
not been run. Whitespace and added-Chinese-character checks passed.
