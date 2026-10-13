# Query latency and connection-pool investigation

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

## Current questions

The investigation must determine a reasonable internal connection-pool capacity
and whether connection reuse introduces avoidable latency under concurrent load.
Evaluate both individual query latency and batch throughput. A connection limit
is not the number of connections actually opened, nor a Ticker concurrency limit.
This work adds no user-facing tuning settings and changes no production scheduler.

## October 10 replacement control pair

The user confirmed the company network and reported a competing download during
the first control pair. Exclude both original October 10 control records from
performance conclusions. Retain them with the exclusion note under
`results/local/20261010_latency_control_exclusions.md`.

The replacement ran baseline first, then candidate, in separate processes:

```sh
.venv/bin/python -m benchmark.workloads.shared_query_benchmark --baseline --no-trace --output benchmark/results/local/20261010_latency_baseline_control_r2.json --concurrency 1 8 16 --repeats 3 --sequential-samples 8
.venv/bin/python -m benchmark.workloads.shared_query_benchmark --no-trace --output benchmark/results/local/20261010_latency_candidate_control_r2.json --concurrency 1 8 16 --repeats 3 --sequential-samples 8
```

Both records completed. Dataset version `2026-10-09T05:15:33Z`, all query
fingerprints, and per-phase downloaded bytes match. Candidate production source
hashes match the working tree. Baseline sources come from commit
`897e9a76fe50e5c929473de4197e97435dd0190b`, release 0.0.62. Transport hooks were
disabled; ordinary benchmark timers and query records remain present.

Each concurrency has three batches. Cold means data extents were cleared before
the batch, with connection and footer/index state retained. Tickers within a
batch may share downloaded extents. Hot means the same workload immediately
repeated without clearing data extents. P95 uses empirical nearest rank over
the combined per-Ticker observations; this is not a population estimate, and
observations sharing a batch are correlated.

| Cold price concurrency | Samples per version | Baseline P50 / P95, seconds | Candidate P50 / P95, seconds | Baseline batch range, seconds | Candidate batch range, seconds |
| --- | --- | --- | --- | --- | --- |
| 1 | 3 | 1.366 / 1.521 | 1.149 / 1.302 | 1.358-1.521 | 1.128-1.302 |
| 8 | 24 | 5.273 / 7.787 | 5.611 / 8.732 | 7.004-7.803 | 6.929-8.739 |
| 16 | 48 | 9.396 / 17.075 | 10.594 / 16.202 | 17.142-17.573 | 16.210-16.828 |

| Hot price concurrency | Baseline P50 / P95, seconds | Candidate P50 / P95, seconds |
| --- | --- | --- |
| 1 | 0.011 / 0.023 | 0.010 / 0.010 |
| 8 | 0.062 / 0.089 | 0.065 / 0.075 |
| 16 | 0.155 / 0.170 | 0.154 / 0.175 |

Constructor plus first price took 5.140 seconds in the baseline and 4.338 seconds
in the candidate. The first price call alone took 2.616 versus 3.287 seconds:
startup work moved into the first query, so constructor timing alone is misleading.
Eight sequential prices took 10.967 versus 10.947 seconds. Two independently
configured clients prepared the same file/index in 2.312 and 2.587 seconds in
the baseline, versus 0.024 and 0.016 seconds in the candidate.

Cold-batch application throughput, including pending-prefetch drain, was
0.777 / 1.445 / 1.303 MB/s in the baseline and 0.922 / 1.394 / 1.374 MB/s in
the candidate for concurrency 1 / 8 / 16. These values are workload throughput,
not wire throughput or an independently measured bandwidth ceiling.

The replacement does not establish a uniform concurrency improvement. At 16
Tickers the candidate completed batches sooner, but its median individual query
latency was higher. Sequential run order and uncontrolled network/CPU variation
prevent attributing small differences to the implementation. No-trace records
do not themselves locate connection-pool or stream waits.

## October 9 instrumented evidence

The completed `20261009_latency_baseline_trace.json` and
`20261009_latency_candidate_trace.json` records have matching dataset versions
and query fingerprints. Each concurrency has two batches. Keep these records
separate from the October 10 controls; comparing different days does not measure
diagnostic overhead.

The relevant call path is:

```text
Ticker.price -> DuckDBClient.query
  -> dataset/version and footer/index preparation
  -> range planning and prefetch scheduling
  -> shared filesystem extent executor
  -> cache validation / pending extent wait
  -> SharedHttpClient / HTTPX
  -> httpcore pool assignment
  -> connect / TLS / HTTP2 initialization if necessary
  -> HTTP2 stream-slot acquisition
  -> headers and first body delivery
  -> remaining body / validation / cache publication
  -> DuckDB execution and DataFrame return
```

This is a dependency outline. Parallel requests, prefetch, cache work and query
execution overlap; the spans do not form an additive exclusive-time breakdown.

Both versions used the default three extent workers in the shared filesystem.
For retained-connection cold price batches with 8, 16 and 32 Tickers, both
versions had a peak of three simultaneous HTTPX Range operations. Each version
reused one price CDN HTTP/2 connection. That connection advertised and used a
100-stream limit. The candidate's physical connection cap of 16 was not exercised
by these price batches.

| Ticker concurrency | Baseline task queue P50 / P95, seconds | Candidate task queue P50 / P95, seconds |
| --- | --- | --- |
| 8 | 2.003 / 5.572 | 2.224 / 5.112 |
| 16 | 4.274 / 13.204 | 6.651 / 24.570 |
| 32 | 11.007 / 26.522 | 11.760 / 26.908 |

These are extent-task queue observations, not per-Ticker percentiles. Across
both 16-Ticker batches, candidate pool waits totaled approximately 0.099 ms
and stream-slot waits 0.162 ms. Queue waiting before HTTP dispatch was substantial;
pool capacity and stream-slot availability were not material waiting points in
this observed workload. This does not prove that more extent workers would
improve latency or throughput.

Single-Ticker retained-connection requests had median first-body delivery latency
of approximately 0.439 seconds in the baseline and 0.438 seconds in the candidate;
median remaining request time after first-body delivery was approximately 0.659
and 0.641 seconds. At 16 Tickers, candidate first-body latency P50 / P95 was
1.434 / 5.558 seconds and remaining request time P50 / P95 was 0.668 / 2.495
seconds. These measurements combine network, proxy, remote service and client
scheduling effects; they do not isolate server processing or physical RTT.

Some native execution-thread requests lack query attribution. Time outside
attributed HTTP includes task/cache waiting and unobserved work, not just CPU.
HTTP/2 read-lock waits overlap other streams' socket work and cannot be added
as exclusive latency. Process CPU time is aggregate across threads.

## Proposed next experiment

First isolate the pool and reuse mechanism from the three-worker extent queue.
Use a diagnostic-only workload calling the existing shared transport against
fixed CDN ranges, with identical payload sizes and complete body consumption.
Keep production limits and range scheduling unchanged.

Cross capacities 1 / 4 / 8 / 16 / 32 with request concurrency 1 / 8 / 16 / 32.
Separate cold connection setup from a ready-connection phase. Repeat and vary
case order to reduce run-order bias. Report actual physical connections, origin,
protocol, pool wait, connect/init lock wait, stream-slot wait, header/first-body
latency, body completion, per-request P50/P95 and batch throughput. A raised cap
that still opens one HTTP/2 connection is not a multi-connection experiment.

Use controlled local HTTP/2 fixtures separately to exercise a saturated stream
limit, slow establishment and concurrent connection replacement; use HTTP/1.1
controls to exercise the physical cap. A verified one-stream fixture already
demonstrates stream waiting on a single connection despite small pool waits.
These controls establish scheduling behavior, not CDN bandwidth performance.

If the live workload keeps reusing one healthy HTTP/2 connection, changing the
cap alone cannot establish whether deliberately opening additional connections
would help. Any such strategy requires a separately discussed and approved
diagnostic comparison. Return to end-to-end Ticker workloads after identifying
the mechanism and controlling the extent queue. Choose a default from measured
latency, throughput and resource use rather than a fixed Ticker-to-connection ratio.

No new experimental runner or production scheduling change is implemented by
this report. Its implementation requires approval of the proposed method.

## Diagnostic regression verification

After both replacement benchmarks completed, the timeline, benchmark import/
percentile, shared-resource and filesystem regressions passed: 134 tests and
three subtests, with one optional network test skipped. The run bound local
fixture ports and did not run concurrently with either benchmark.

Relevant covered edge cases include a one-stream HTTP/2 peer with three waiting
requests, overlapping HTTP intervals, prefetch query-context propagation,
server-closed connection replacement, unchanged failures and hook restoration,
concurrent GOAWAY recovery, and failed single-flight preparation followed by
retry. The proposed capacity experiment should additionally distinguish cold
proxy-tunnel establishment from ready HTTP/2 reuse and verify that a request
timeout or incomplete body cannot leave a connection or stream permanently held.
