# Office-network single-query CPU diagnosis

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

## Finding

Native stack sampling locates the observed CPU hotspot in DuckDB's Python
pending-query execution loop and its repeated GIL transitions. The same
hotspot appears with both the upstream and coordinated HTTP/2 receivers.
This establishes that the high-CPU symptom is not unique to the coordinator;
it does not establish equal overhead or explain every prior latency change.

The network event-loop thread spends most of the sampled observations in
`kevent`. DuckDB scan workers are observed waiting in `PythonFilesystem::Read`
through Python condition-variable waits, while the query caller repeatedly
enters `CompletePendingQuery`, `ExecuteTask`, and GIL acquire/release paths.
This is consistent with active polling while another worker waits for input.

## Method and integrity

- User-confirmed office network, 2026-10-12; existing routing and TLS unchanged.
- Current product code and default pool policy, without diagnostic hooks.
- Thirty sequential one-query batches per sampled run, using the existing
  mixed benchmark with concurrency one. Each batch calls PDD `price` after
  footer/index preparation and data-cache clearing.
- macOS `sample` captures native stacks for ten seconds at a requested
  five-millisecond interval, starting fifteen seconds after process launch.
  Sampling and benchmark launch share one shell to avoid a stale process ID.
- The sampling interval overlaps measured query batches, not just startup:
  transient query-worker stacks include `DuckDBPyRelation::FetchDF` and
  `CompletePendingQuery`.
- Sampled runs started at 10:06:38 and 10:48:24 Asia/Shanghai. They are
  diagnostic observations, not a controlled latency A/B comparison.
- All 60 queries succeeded, without cache fallback, new measured connections,
  or connection-close errors. Every batch downloaded 1,261,289 bytes, and
  result fingerprints match across both runs.
- Dataset version: `2026-10-11T04:59:20Z`. Recorded product-module hashes
  match the working tree at analysis time. DuckDB version: 1.5.3.

## Observations

| Metric | Upstream receiver | Coordinated receiver |
| --- | ---: | ---: |
| Measured single-query batches | 30 | 30 |
| Median process CPU per batch, s | 1.194918 | 1.325651 |
| Median batch wall time, s | 1.258220 | 1.419701 |
| Batches above 0.5 process CPU seconds | 21 | 22 |
| Maximum cumulative pool-acquisition time per batch, s | 0.000026 | 0.000040 |
| Query-thread stack observations | 1,714 | 1,732 |
| Observations containing `CompletePendingQuery` | 1,700 | 1,720 |
| Event-loop thread observations in `kevent` | 1,603 / 1,730 | 1,665 / 1,741 |

The 0.5 CPU-second threshold is a descriptive split for this workload, not a
product threshold. CPU is summed across process threads and includes the
benchmark's pool sampler. Native sample counts include blocked threads and
are not percentages of CPU consumption. The pending-query observations show
both executable polling frames and GIL synchronization; the call-stack share
must not be presented as an exclusive CPU attribution.

No `WaitForTask` frame appears in either sample. This supports the polling
interpretation but is not a trace of every executed branch or return value.

## Source-level explanation

The pinned [DuckDB Python 1.5.3 implementation](https://github.com/duckdb/duckdb-python/blob/v1.5.3/src/duckdb_py/pyconnection.cpp#L513-L532)
repeatedly calls `ExecuteTask`, briefly acquires the GIL to check Python
signals, and calls `WaitForTask` only for the `BLOCKED` result.

The matching [DuckDB executor](https://github.com/duckdb/duckdb/blob/v1.5.3/src/parallel/executor.cpp#L509-L540)
can return `NO_TASKS_AVAILABLE` while pipelines are incomplete and no queued
or explicitly descheduled task is available. A synchronous filesystem read
occupied on another worker can leave the caller in this state. The Python
loop then immediately checks again. This return-state explanation is an
inference combining source and observed stacks; return values were not
instrumented in the running binary.

Simply calling `WaitForTask` for that result is not a verified fix: the
[same executor's waiting method](https://github.com/duckdb/duckdb/blob/v1.5.3/src/parallel/executor.cpp#L433-L452)
returns immediately when its descheduled-task collection is empty. A general
fix requires a correct task-completion or availability notification path,
including cancellation, rather than just broadening one condition.

An existing upstream [issue #22178](https://github.com/duckdb/duckdb/issues/22178)
reports a related `NO_TASKS_AVAILABLE` busy-spin in the native pending-query
loop. Its Java/Postgres reproduction is different from this Python/fsspec
workload and is corroborating context, not proof of an identical trigger.

## Interpretation and next validation

The original single-query CPU medians should not be interpreted as proof
that the receive coordinator introduced the CPU issue. Both receivers expose
the same pending-query/GIL hotspot in the repeated diagnostic runs. The
underlying waiting behavior should be isolated before retuning the pool.

The next proposed validation is an offline minimal reproduction with a
deliberately delayed synchronous fsspec read, measuring CPU while the read is
blocked and checking result correctness. It should distinguish caller-owned
and worker-owned execution, then exercise concurrent queries and cancellation.
Only after that reproduction should a general waiting/wakeup fix be designed
or an upstream fix evaluated. No product patch, dependency upgrade, thread
default change, or additional user configuration was made in this diagnosis.

Follow-up: the [offline reproduction](DUCKDB_WAIT_REPRO.md) now reproduces
ownership-dependent CPU consumption using only DuckDB, fsspec and synthetic
Parquet bytes, and verifies concurrent results, cancellation and recovery.

## Local artifacts

These raw files are ignored by Git:

- `results/local/20261012_office_cpu_coordinated_c.json`
- `results/local/20261012_office_cpu_coordinated_c.log`
- `results/local/20261012_office_cpu_coordinated_c.sample.txt`
- `results/local/20261012_office_cpu_upstream_a.json`
- `results/local/20261012_office_cpu_upstream_a.log`
- `results/local/20261012_office_cpu_upstream_a.sample.txt`

Earlier `20261012_office_cpu_coordinated_a.json` and
`20261012_office_cpu_coordinated_b.json` completed 30 and 60 queries, but
attempted process attachment happened too late. They contain no successful
native sample despite their planned-sampling network labels and are excluded
from the sampled comparison above. Their process CPU medians were 1.404 s
and 1.227 s respectively, confirming symptom recurrence only.
