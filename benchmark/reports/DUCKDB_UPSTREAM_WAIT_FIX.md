# Official DuckDB waiting fix evaluation

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

This report records the initial investigation before adoption. See the
[upgrade validation](DUCKDB_2_UPGRADE.md) for the subsequent compatibility fix,
home-network results, and dependency upgrade.

## Decision and scope

The official `2.0.0.dev2610011535` wheel resolves the observed high-CPU waiting
symptom in the existing offline reproduction while retaining parallel compute.
This establishes an upstream solution path without maintaining a DuckDB fork.
It does not establish production readiness or faster end-to-end API queries.

The project still pins DuckDB 1.5.3. No product source, dependency, configuration,
test assertion, or benchmark implementation was changed in this investigation.
The candidate was installed into an isolated directory under `/private/tmp`.
The user's current network is home; all measurements below are offline.
Earlier office-network API timings are not combined with this evaluation.

## Source findings

- [PR #24132](https://github.com/duckdb/duckdb/pull/24132), merged July 27, 2026,
  makes `WaitForTask` wait when background workers own the remaining work and
  introduces task-completion notification. The wait remains bounded at 20 ms;
  notifications can wake it earlier.
- [PR #25418](https://github.com/duckdb/duckdb/pull/25418), merged September 7,
  fixes a subsequent executor regression involving partially processed work.
  The reporter confirmed the correction in
  [issue #25282](https://github.com/duckdb/duckdb/issues/25282).
- The exact candidate's
  [core implementation](https://github.com/duckdb/duckdb/blob/96063b9e39749cc0f087bb11501d7edbee527957/src/parallel/executor.cpp#L335)
  includes completion notifications and bounded waiting. Its commit descends
  from the regression fix, as verified through GitHub's compare API.
- The corresponding Python
  [materialized-result loop](https://github.com/duckdb/duckdb-python/blob/62323e5d924f0ce9598de88a83ab31b9801fb831/src/pyconnection.cpp#L518)
  and
  [streaming-result loop](https://github.com/duckdb/duckdb-python/blob/62323e5d924f0ce9598de88a83ab31b9801fb831/src/pyresult.cpp#L131)
  both handle `NO_TASKS_AVAILABLE` by waiting.
- The latest official Python release checked on October 12 was
  [1.5.6](https://github.com/duckdb/duckdb-python/releases/tag/v1.5.6).
  Its [Python loop](https://github.com/duckdb/duckdb-python/blob/v1.5.6/src/duckdb_py/pyconnection.cpp#L506)
  waits only for `BLOCKED`, and its
  [core wait](https://github.com/duckdb/duckdb/blob/v1.5.6/src/parallel/executor.cpp#L424)
  returns immediately when the descheduled-task set is empty. Merely upgrading
  from 1.5.3 to 1.5.6 does not supply this complete waiting fix.

The remedy belongs to both the native executor's notification mechanism and
the binding's waiting loop. Sleeping around a synchronous Python query call
does not change its internal loop. Predicting all SQL reads in advance is not
a general substitute for this mechanism.

## Candidate provenance

- Python: 3.11.10, macOS arm64.
- Package: `duckdb==2.0.0.dev2610011535`, downloaded from official PyPI.
- Wheel: `duckdb-2.0.0.dev2610011535-cp311-cp311-macosx_11_0_arm64.whl`.
- Wheel SHA-256: `bb327f3d7a7998549c5d977989d5651e32c85ec0d77e9379668e8874ceb02a53`.
- Python repository commit: `62323e5d924f0ce9598de88a83ab31b9801fb831`.
- Its core submodule: `96063b9e39749cc0f087bb11501d7edbee527957`.
- Runtime `PRAGMA version`: `v2.0.0-alpha43763`, `96063b9e39`, `Cyanoptera`.
- Isolated import: `/private/tmp/defeatbeta-duckdb-upstream-20261012/site/duckdb/__init__.py`.

This is an official development build, not a stable release or a custom patch.

## Held-read reproduction

The unchanged `benchmark.diagnostics.duckdb_wait_repro` uses synthetic Parquet and fsspec.
Data reads wait behind an Event; metadata reads remain available. Every case
has its own spawned process and deadline. The matrix covers 1/4 configured
threads, 1/4 callers, 0.3/0.9 seconds held reads, and 12 repetitions.

All 96 cases and 240 queries completed correctly. Every candidate read observed
at the end of the held interval belonged to a non-caller thread. Process CPU
divided by held wall time was at most 0.005074 across the matrix.

The table reports medians over 12 cases per cell, with four configured threads
and four concurrent queries. The 1.5.3 observations come from the earlier
offline reference, not a newly interleaved version comparison.

| Held wall interval | 1.5.3 process CPU | Candidate process CPU | Candidate completion after release |
| --- | ---: | ---: | ---: |
| 0.3 s | 0.512868 s | 0.0010235 s | 0.004784 s |
| 0.9 s | 1.301227 s | 0.0033215 s | 0.002917 s |

Maximum completion after release was 0.011267 seconds across all candidate
cases. This interval includes finishing the query and collecting its result;
it is not a direct condition-variable wakeup measurement or a latency bound.

Both versions used the same reproduction source and logical fixture. Each
version wrote its own Parquet bytes: 524644 bytes for 1.5.3 and 524673 for the
candidate, with different hashes. Scheduling and reader ownership also differ.
The observations demonstrate the symptom disappearing in the candidate, not
an isolated performance attribution to one upstream commit.

## Cancellation

Twelve additional cases covered 1/4 threads and 1/4 callers, with three
repetitions and a 0.3-second held read. All 12 targeted queries raised
`InterruptException`, all 18 other queries returned correct results, and all
12 cancelled cursors subsequently returned 42 from a new query.

None of the cancelled queries finished before its synchronous read was
released. The upstream fix does not forcibly preempt arbitrary Python I/O.

## Compute control

The unchanged `benchmark.diagnostics.duckdb_cpu_comparison` ran sequentially in ABBA order:
1.5.3, candidate, candidate, 1.5.3. Each process used four configured threads,
1/4 concurrent callers, 16,777,216 rows per query, and four rounds. All 32 cases
and 80 queries matched the independent integer reference and one fingerprint.

Values are medians over eight cases per version/concurrency.

| Concurrent queries | 1.5.3 wall | Candidate wall | 1.5.3 process CPU | Candidate process CPU |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0.063992 s | 0.066158 s | 0.250812 s | 0.257838 s |
| 4 | 0.163481 s | 0.170822 s | 1.012790 s | 1.017646 s |

The candidate retained multi-core computation, but median wall time was about
3.4% and 4.5% higher respectively. One candidate four-query case took 0.243365
seconds; its other observations ranged from 0.164438 to 0.173856 seconds.
Host activity was not controlled. These samples do not prove equivalence or
a universal regression; they do rule out claiming an across-the-board speedup.

## Existing offline suite

The candidate ran the existing 367-test offline suite in 33.321 seconds:
365 passed, one failed, and one optional public-network test was skipped.
The failure is the diagnostic assertion that `threads=1` necessarily executes
the read on the caller thread. Candidate results were correct, but observed
thread ownership differs. The configured thread value was separately checked
on both a connection and its cursor and remained 1.

The assertion was not changed to make this run pass. Any adoption should first
review execution assumptions and validate observable contracts. The initial
sandboxed suite could not bind local test-server ports; the reported result is
the authorized rerun with local networking available.

## Adoption boundaries

The preferred direction is the official upstream waiting mechanism, preserving
parallel execution. Stable adoption can use an official release containing
the complete fix, or an official backport if upstream provides one. No backport
availability or release date was established here.

Before changing project dependencies, validate DataFrame and streaming paths,
HTTPFS extension availability, all supported platforms, error cleanup and
cancellation, and same-dataset API latency/throughput on the home network.
The offline suite does not replace those integration checks. Do not infer
bandwidth saturation or query speedup from reduced waiting CPU.

## Artifacts

Raw output is ignored by Git under `benchmark/results/local/`:

- `20261012_upstream_2dev_smoke.json`
- `20261012_upstream_2dev_wait.json`
- `20261012_upstream_2dev_cancel.json`
- `20261012_upstream_cpu_a_153.json`
- `20261012_upstream_cpu_b_2dev.json`
- `20261012_upstream_cpu_c_2dev.json`
- `20261012_upstream_cpu_d_153.json`
- `20261012_upstream_2dev_tests_unrestricted.log`

Reference: `20261012_duckdb_wait_offline_final.json`.

Reproduce against an isolated installation of the exact candidate:

```sh
PYTHONPATH=/private/tmp/defeatbeta-duckdb-upstream-20261012/site \
  .venv/bin/python -m benchmark.diagnostics.duckdb_wait_repro \
  --output NEW_UNIQUE_WAIT_RESULT.json --threads 1 4 --queries 1 4 \
  --delays 0.3 0.9 --repeats 12
```

Add `--cancel`, use `--delays 0.3 --repeats 3`, and choose a new output path for
the cancellation matrix. Run compute comparisons sequentially with and without
the isolated `PYTHONPATH`, using separate output paths and the options above.
