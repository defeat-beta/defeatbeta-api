# DuckDB caller-only execution evaluation

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

## Decision

Keep the product default at four DuckDB threads. A single-thread database
substantially reduces process CPU for the measured remote API workload, but
does not improve latency or throughput uniformly. It also gives up useful
intra-query parallelism on a compute-heavy workload. These results do not
support adopting `threads=1` as a general performance fix.

No product code, dependency, pool policy or default changed in this evaluation.
The new thread-count argument belongs only to the mixed-API benchmark. DuckDB
remains the official 1.5.3 package; no native patch or custom build is used.

## What is being compared

Both candidates expose the same synchronous Python query calls. With one
DuckDB thread, each query caller executes its own work and can block in a
synchronous read. With four, background workers can own a read while the
caller waits for task completion. The prior
[isolated waiting reproduction](DUCKDB_WAIT_REPRO.md) established the high-CPU
behavior for the latter ownership pattern without a network or DefeatBeta code.

A single-thread database does not serialize separate callers. The tests use
separate cursors on a shared database and require all four queries to enter
their read gates before releasing any gate. Both thread configurations pass.
The product's network executor and HTTP stream reservations remain separate
from DuckDB's internal query execution threads.

## Office-network API comparison

Four independent processes ran sequentially on 2026-10-12 in order 4, 1, 1, 4
DuckDB threads. Their start times were 14:14:33, 14:16:20, 14:18:05 and 14:19:50
Asia/Shanghai. Each process ran two batches at each concurrency of 1, 32 and
128. This yields four batch observations per configuration/concurrency and
24 batches overall. No other test or benchmark was run concurrently by the
agent. Other host activity and external network load were not controlled.

The workload is unchanged from the existing mixed-API benchmark: one `price`
query at concurrency one; distinct symbol/API pairs across `price`, `info`,
`calendar` and `dividends` at higher concurrency. All Tickers in a process use
one shared DuckDB client. The requested thread setting is read back and checked
before any measurements.

Footer/index objects are prepared before measurements. Data blocks are cleared
before every batch. DuckDB's external file cache is disabled and its metadata
cache remains enabled. HTTP receive coordination is enabled in both candidates.
Diagnostic hooks are disabled; query timers, process CPU measurement and the
5 ms connection-pool sampler remain active. The first 32-query batch can expand
the pool; later batches reuse its connections. Constructor and warmup are not
included in the table.

Both candidates use core 4 connections per origin, global maximum 16 connections,
4 local streams per connection, 4 simultaneous connection initializations,
16 cache download workers and 60 seconds surplus idle timeout.

### Integrity

- All 1,288 measured queries succeeded without uncached fallback or reported
  connection-close errors.
- All 128 distinct symbol/API result fingerprints match across all runs.
- All reports use dataset version `2026-10-12T05:39:55Z`, reflecting the remote
  update reported by the user. Older network measurements are not pooled here.
- Downloaded bytes per batch match across both candidates: 1,261,289 at
  concurrency 1; 14,485,750 at 32; 47,478,981 at 128. Measured batches downloaded
  505,808,160 bytes, excluding warmups.
- All recorded product and diagnostic source hashes match across the four runs
  and match the sources used at analysis time.
- Version metadata and output fingerprints are consistency checks; this
  benchmark does not replace `main` URLs with an immutable dataset revision.

### Results

Every cell below is the median of four batch observations. P95 is computed
within each batch first. For concurrency one, P95 is just that query's latency.
CPU seconds are summed over all process threads, including network workers
and the sampler; they are not exclusive DuckDB CPU measurements.

| Concurrent queries | Threads 4 P95, s | Threads 1 P95, s | Threads 4 batch wall, s | Threads 1 batch wall, s | Threads 4 CPU, s | Threads 1 CPU, s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1.822628 | 1.439144 | 1.822828 | 1.439561 | 1.837971 | 0.150712 |
| 32 | 10.180052 | 9.400663 | 10.251373 | 10.240430 | 7.031691 | 1.528127 |
| 128 | 29.242060 | 29.539902 | 31.089163 | 34.069109 | 32.069947 | 5.860745 |

Single-query latency decreased about 21.0% in this sample. The 32-query batch
wall time was essentially unchanged. At 128 queries the candidate's median
batch wall time increased 9.6%, while its P95 increased about 1.0%. Reduced
process CPU therefore did not translate into uniformly faster completion.

| Concurrent queries | Threads 4 application MB/s | Threads 1 application MB/s | Threads 4 P95 range, s | Threads 1 P95 range, s |
| ---: | ---: | ---: | --- | --- |
| 1 | 0.691953 | 0.876504 | 1.788016-2.209840 | 1.263309-1.527328 |
| 32 | 1.413052 | 1.416461 | 9.741566-14.509707 | 8.864663-10.079959 |
| 128 | 1.527188 | 1.393672 | 28.019415-30.603913 | 29.201200-30.433732 |

Application throughput is downloaded bytes divided by batch wall plus pending
prefetch drain, in decimal MB/s. It is not physical-link bandwidth. Both
candidates reached 16 observed stream reservations at 128 queries. This
establishes retained concurrent network use, not bandwidth saturation.

Four-thread single-query CPU ranged from 0.124747 to 2.209133 seconds:
the busy-wait symptom is not present in every execution. One-thread CPU
ranged from 0.113162 to 0.187425 seconds.
The offline ownership evidence supports the mechanism, while these online
timings alone cannot attribute every difference to DuckDB. ABBA ordering and
four samples per cell do not eliminate network, CDN or scheduler variation.

## Compute-heavy control

`benchmark.diagnostics.duckdb_cpu_comparison` builds an in-memory table of 16,777,216
deterministic BIGINT values, performs one warmup, and runs a grouped integer
aggregate. A Python reference derives exact results from periodic value
frequencies, independently of SQL. No network, Parquet reader or product code
participates in this control.

Every case has a fresh spawned process and database, with a parent deadline.
Concurrent queries use separate cursors and a start barrier. Table construction,
warmup, result validation and teardown are outside the timed interval. Thread
and query-concurrency order are reversed in alternating rounds. Eight rounds
produce 32 cases and 80 queries, all correct with the same result fingerprint.

Environment: macOS, Python 3.11.10, DuckDB 1.5.3. Values below are medians of
eight cases. Throughput is completed queries per second, not bytes per second.

| Concurrent queries | Threads 4 batch wall, s | Threads 1 batch wall, s | Threads 4 CPU, s | Threads 1 CPU, s | Threads 4 queries/s | Threads 1 queries/s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.051388 | 0.183119 | 0.201698 | 0.182719 | 19.460 | 5.461 |
| 4 | 0.137772 | 0.202402 | 0.821323 | 0.786701 | 29.035 | 19.763 |

The caller-only single-query case takes about 3.56 times as long. Four concurrent
queries also finish more slowly, with about 31.9% lower throughput in this
control. Conversely, approximately 0.787 CPU seconds in 0.202 wall seconds
with `threads=1` confirms that concurrent callers still use multiple cores.
This synthetic workload exposes a tradeoff; it does not predict the magnitude
for every public API or SQL query.

## Tests, boundaries and reproduction

The full offline suite completed 367 tests in 28.126 seconds: 366 passed and
one optional public-network test was skipped. The additional tests cover:

- Exact reference results for partial periods and missing groups.
- Identical shared-database results with 1/4 internal threads and 1/4 callers.
- Concurrent held reads in both execution modes.
- Targeted cancellation without cancelling the other caller, followed by
  successful cursor reuse in both modes.
- Hard-deadline child-process cleanup.

Cancellation still cannot forcibly preempt an arbitrary synchronous Python
read. CPU timing thresholds are not CI assertions. No native waiting fix,
hot-cache API performance guarantee or cross-platform performance claim is
established by these checks.

```sh
.venv/bin/python -m benchmark.diagnostics.duckdb_cpu_comparison \
  --output benchmark/results/local/NEW_UNIQUE_CPU_RESULT.json \
  --threads 4 1 --queries 1 4 --rows 16777216 --rounds 8

.venv/bin/python -m benchmark.workloads.http_pool_mixed \
  --output benchmark/results/local/NEW_UNIQUE_NETWORK_RESULT.json \
  --network-label 'Office network; record current date' \
  --budgets 16 --concurrency 1 32 128 --cache-modes cached \
  --rounds 1 --batches-per-concurrency 2 --no-hooks \
  --receive-mode coordinated --duckdb-threads 4
```

Repeat the network command in separate processes with thread counts 4, 1, 1,
4 and distinct output paths. Check dataset versions, byte counts, source hashes
and result fingerprints before combining any observations.

Raw artifacts are ignored by Git:

- `results/local/20261012_duckdb_cpu_candidate.json`
- `results/local/20261012_office_threads_a.json` (4 threads)
- `results/local/20261012_office_threads_b.json` (1 thread)
- `results/local/20261012_office_threads_c.json` (1 thread)
- `results/local/20261012_office_threads_d.json` (4 threads)
