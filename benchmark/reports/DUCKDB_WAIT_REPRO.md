# Offline DuckDB synchronous-read waiting reproduction

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

## Result

The high-CPU waiting symptom is reproduced without HTTP, a CDN, DefeatBeta's
connection pool, its cache filesystem, or its receive coordinator. Only DuckDB,
fsspec and locally generated Parquet bytes participate.

Execution ownership separates two behaviors. When the query caller performs
the synchronous read itself, the caller blocks and process CPU stays near zero.
When a DuckDB worker performs the read, the query caller can consume CPU
throughout the blocked interval. Caller-thread CPU measured over the query
closely accounts for the process CPU measured during the held-read interval.
The behavior matches the pending-query/GIL hotspot observed in the preceding
[native stack diagnosis](HTTP2_OFFICE_CPU_DIAGNOSIS.md).

This confirms a dependency-level waiting problem. It does not prove that every
prior latency difference was caused by this problem, or measure the improvement
that a future fix would deliver. No product code, dependency or default was
changed. A one-thread database is a diagnostic control, not a proposed default.

## Isolation and measurement

The reproducer generates a 524,644-byte, single-row-group Parquet file with
32,768 deterministic integer rows. A small fsspec filesystem serves the bytes
from memory. Magic-byte and footer reads remain immediate. Data reads enter
a `threading.Event` gate and cannot return until the controller releases them.

Each query computes an aggregate with a row predicate. Expected count and sum
are calculated independently, and every successful result must match them.
Concurrent queries use separate cursors and separate read gates on one DuckDB
database. Reader identities are compared with the corresponding caller identity;
the experiment does not force DuckDB's choice of execution thread.

Every case has its own spawned process and database. After every query has
entered a data read, the controller records process CPU, waits 0.3 or 0.9 seconds,
and records process CPU again before releasing the reads. Startup, query
planning and post-release processing are excluded from this CPU interval.
The report also retains each caller's total query thread CPU for attribution.

The parent enforces a hard process deadline and terminates an unresponsive
child. A gate also has a safety timeout. Timing thresholds are not asserted
by CI: scheduling, hardware and shared-host load affect CPU measurements.

Environment: macOS, Python 3.11.10, DuckDB 1.5.3, fsspec 2026.9.0.
The remote dataset update reported by the user has no effect on this fixture.

## Final measurement matrix

The final script ran twelve repetitions for each combination of database
threads (1 or 4), query concurrency (1 or 4), and requested blocked duration
(0.3 or 0.9 seconds). All 96 cases and all 240 queries completed correctly.
The source hash in the artifact matches the final reproducer.

Observed ownership varies between executions. The table groups observations
by ownership rather than averaging the two distinct behaviors together.
CPU/wall is process CPU divided by the actual held-read wall interval.

| Database threads | Queries | Reads owned by callers | Requested hold, s | Cases | Median held CPU, s | Median CPU/wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 1 | 0.3 | 12 | 0.000112 | 0.000367 |
| 1 | 1 | 1 | 0.9 | 12 | 0.000129 | 0.000143 |
| 1 | 4 | 4 | 0.3 | 12 | 0.000071 | 0.000231 |
| 1 | 4 | 4 | 0.9 | 12 | 0.000107 | 0.000118 |
| 4 | 1 | 0 | 0.3 | 1 | 0.302082 | 0.990189 |
| 4 | 1 | 1 | 0.3 | 11 | 0.000108 | 0.000354 |
| 4 | 1 | 1 | 0.9 | 12 | 0.000168 | 0.000186 |
| 4 | 4 | 1 | 0.3 | 9 | 0.513624 | 1.697089 |
| 4 | 4 | 2 | 0.3 | 1 | 0.405307 | 1.328648 |
| 4 | 4 | 3 | 0.3 | 2 | 0.248175 | 0.813888 |
| 4 | 4 | 1 | 0.9 | 6 | 1.505263 | 1.663501 |
| 4 | 4 | 2 | 0.9 | 3 | 1.253177 | 1.384866 |
| 4 | 4 | 3 | 0.9 | 2 | 0.901452 | 0.997135 |
| 4 | 4 | 4 | 0.9 | 1 | 0.000102 | 0.000113 |

For four queries with three worker-owned reads, tripling the controlled wait
increased median held CPU from 0.514 to 1.505 seconds. The corresponding median
sum of caller-thread CPU was 0.520 and 1.511 seconds. This locates the extra
work in the callers, while their input reads remain blocked.

Every case in which all reads were caller-owned consumed less than 0.000552
process CPU seconds during the held interval. No worker-owned single-query
case occurred at the 0.9-second setting in this final matrix; the table does
not manufacture one from earlier runs. Ownership frequencies in this synthetic
fixture are not estimates of production occurrence rates.

## Cancellation and recovery

A separate final run covered twelve cancellation cases with 1 or 4 database
threads and 1 or 4 concurrent queries, three repetitions per combination.
It requested interruption of query zero while all reads were still held, waited
0.1 seconds to observe completion, and then released the read gates.

- All twelve interrupted queries raised `InterruptException`.
- All eighteen non-target queries returned the expected results.
- All twelve interrupted cursors subsequently executed `SELECT 42` correctly.
- The interrupt call returned within 0.000031 seconds in every case.
- No interrupted query completed while its synchronous read remained held.
- After release, completion of the case including cursor recovery took at most
  0.009846 seconds.

Interruption therefore does not preempt this synchronous Python read. A future
waiting fix must retain cancellation and wakeup correctness without assuming
that `interrupt()` can forcibly release an arbitrary filesystem callback.

## Source interpretation and fix boundary

The pinned [Python pending-query loop](https://github.com/duckdb/duckdb-python/blob/v1.5.3/src/duckdb_py/pyconnection.cpp#L513-L532)
checks execution repeatedly and reacquires the GIL for signal handling. It waits
only for `BLOCKED`. The [executor](https://github.com/duckdb/duckdb/blob/v1.5.3/src/parallel/executor.cpp#L509-L540)
can report `NO_TASKS_AVAILABLE` while another worker still owns unfinished work.
The observed ownership-dependent CPU use supports this explanation. This
reproducer does not instrument the native return enum directly.

The next design boundary is task readiness and completion notification in
DuckDB's waiting path. Merely calling its existing `WaitForTask` for more
states is not an established solution: that method returns immediately when
its explicitly descheduled-task set is empty. A proposed change must preserve
parallel execution, task completion, errors, interruption and cursor reuse.

## Tests and reproduction

Four automated tests cover delayed reads and results, reader ownership under
the single-thread control, concurrent gate isolation, interruption of one query
without affecting another, cursor recovery, and parent-deadline child cleanup.
They run in the dataset-cache CI workflow without any public network access.

```sh
.venv/bin/python -m unittest test.test_duckdb_wait_repro -v

.venv/bin/python -m benchmark.diagnostics.duckdb_wait_repro \
  --output benchmark/results/local/NEW_UNIQUE_WAIT.json \
  --threads 1 4 --queries 1 4 --delays 0.3 0.9 --repeats 12

.venv/bin/python -m benchmark.diagnostics.duckdb_wait_repro \
  --output benchmark/results/local/NEW_UNIQUE_CANCEL.json \
  --threads 1 4 --queries 1 4 --delays 0.3 --repeats 3 --cancel
```

Final raw artifacts, ignored by Git:

- `results/local/20261012_duckdb_wait_offline_final.json`
- `results/local/20261012_duckdb_wait_offline_cancel_final.json`

Earlier `20261012_duckdb_wait_offline_a.json` and
`20261012_duckdb_wait_offline_single.json` are preliminary observations from
before the final reader-snapshot locking change. They are not pooled into the
tables above.

## Execution-policy follow-up

The [caller-only execution evaluation](DUCKDB_EXECUTION_COMPARISON.md) compares
one and four DuckDB threads on real office-network APIs and a compute-heavy
control. It retains the product default because lower waiting CPU does not
establish a general latency or throughput improvement.
