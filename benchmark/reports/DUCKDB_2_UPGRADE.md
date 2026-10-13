# DuckDB 2.0 development build upgrade

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

## Outcome

On 2026-10-12, after isolated compatibility and performance validation, the
project dependency and local editable environment were upgraded from 1.5.3 to
the official `2.0.0.dev2610011535` wheel. Both `pyproject.toml` and
`requirements.txt` pin that exact version. This is a development release, not
the stable 2.0 release. Python remains `>=3.11` and the DuckDB thread default
remains four.

The [upstream investigation](DUCKDB_UPSTREAM_WAIT_FIX.md) records the executor
and binding fixes, wheel hash, native commit, controlled waiting reproduction,
and compute-only comparison. No DuckDB fork or native patch is maintained.

The validation supports adoption for the tested workloads. It does not claim
that every query is faster or that physical-link bandwidth is saturated.

## Compatibility changes

The live integration tests initially passed but emitted native binding leak
warnings during interpreter shutdown. An offline subprocess reproduced the
warning after registering the project's cache filesystem on a shared client.
A plain connection and a client without the filesystem did not reproduce it;
explicit client close removed it. The registered filesystem holds a bound
resolver referencing its client, while the client owns the connection and
filesystem. Shutdown now closes shared clients before native finalization.

The shared-client registry is detached under its lock and clients are closed
outside that lock. Cleanup attempts every client even if one close fails, then
reports the first exception. Empty and repeated cleanup are safe. The atexit
callback is registered after shared network resources, so reverse callback
order closes query clients first. Normal query allocation and reuse are
unchanged. This covers normal interpreter shutdown, not forced termination.

The regression was added and observed failing before the fix. It checks an
actual subprocess using DuckDB and cachefs, automatic close exactly once, and
absence of native binding leak warnings. A separate test covers a failed close,
cleanup of the remaining client, registry draining, and repeated cleanup.
Both regressions pass against 1.5.3 and the candidate.

The waiting diagnostic formerly asserted that `threads=1` must execute a read
on the caller thread. That assertion fails on the candidate despite correct
query results. It now checks the actual thread setting on each cursor and
retains reader ownership as diagnostic data. Concurrent results, cancellation,
cursor recovery, and deadline assertions remain in place. The extra settings
query precedes the held-read measurement. Earlier benchmark artifacts retain
their historical source hashes and are not rewritten.

## Home-network comparison

Four benchmark processes ran in ABBA version order: 1.5.3, candidate, candidate,
1.5.3. Each ran two batches at concurrency 1, 32, and 128. This is 24 measured
batches and 1,288 successful queries, with four observations per table cell.
The one-query workload is PDD `price`; concurrent workloads balance `price`,
`info`, `calendar`, and `dividends` across distinct symbol/API pairs.

All reports use dataset version `2026-10-12T05:39:55Z`, identical transport and
benchmark source hashes, and identical results for all 128 distinct pairs.
There were no recorded failed queries, cache fallbacks, or connection-close
errors. This comparison preceded the exit-only cleanup change. Benchmark
processes ran sequentially; a 0.930-second offline diagnostic also ran during
the first process's startup period. Other host and network activity was not
controlled. These are descriptive observations, not a causal isolation of one
upstream commit.

Both versions use four DuckDB threads, four core connections per origin,
sixteen total connections, four local streams per connection, sixteen cache
workers, and coordinated HTTP/2 receives. Footer/index objects are prepared;
data extents are cleared before each batch. The external DuckDB file cache is
disabled. Constructors, warmup, and result fingerprinting are outside timing.

All table values are medians. CPU is process CPU across all threads. P95 is
computed within each batch before taking the median across batches.

| Concurrent queries | 1.5.3 wall, s | Candidate wall, s | 1.5.3 CPU, s | Candidate CPU, s | 1.5.3 P95, s | Candidate P95, s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.848190 | 0.544120 | 0.643726 | 0.075588 | 0.847964 | 0.543932 |
| 32 | 2.369881 | 2.071376 | 2.116551 | 0.856719 | 2.296125 | 1.967044 |
| 128 | 4.939406 | 4.215654 | 6.548955 | 2.869885 | 3.547731 | 3.769774 |

Median batch wall decreased approximately 35.8%, 12.6%, and 14.7%. Median CPU
decreased approximately 88.3%, 59.5%, and 56.2%. At 128 queries, median P95
increased about 6.3%; this is not an across-the-board latency improvement.
Candidate batch wall ranges were 0.5395-0.5794, 1.3464-2.6157, and
3.5350-5.6302 seconds; baseline ranges were 0.5310-0.9965, 1.4149-2.8331,
and 3.9781-6.2674 seconds respectively.

Logical results match, but byte workloads differ slightly. Baseline/candidate
downloaded bytes are 1,261,289/1,261,289 at concurrency 1,
14,485,750/14,485,190 at 32, and 47,478,981/47,471,513 at 128. Engine versions
can request different ranges. URLs still use `main`; version metadata and
fingerprints are consistency checks rather than immutable revision pinning.
No office-network observations are pooled with these home-network runs.

## Additional validation

- The candidate initialized and loaded the official HTTPFS extension from the
  `core` repository using the existing project settings.
- Cached and uncached paths ran another 322 successful queries at concurrency
  1/32/128. All 128 distinct result fingerprints matched across paths, with no
  reported cache fallback or connection-close error. Peak stream reservations
  reached 16 for cached reads and 43 for uncached reads; these are observations,
  not a change to limits. The process exited without binding leak warnings.
- The final offline suite ran 369 tests in 30.591 seconds: 368 passed and one
  optional public-network test was skipped. This includes the new shutdown
  regressions, held reads, cancellation, cache consistency, and HTTP/2 tests.
- After installing the candidate into the actual project environment, four
  live integration tests passed in 8.024 seconds with no shutdown warnings.
  They cover BABA price and nested transcript queries, AAPL/PDD/ZTS price,
  concurrent BABA info, and industry-peer market-capitalization queries.
- Runtime import resolves to the project's `.venv`, not the isolated target.
  Native version is `v2.0.0-alpha43763`, commit `96063b9e39`. Editable package
  metadata and the pre-existing local egg-info were refreshed and agree on the
  pin. `pip check` reports no broken requirements.
- Official Python 3.11 wheels were verified available and not yanked for
  macOS, Linux, and Windows architectures. Runtime testing here was macOS
  arm64 only. The existing cross-platform CI has not been executed remotely
  during this local validation.

The earlier compute control showed retained multi-core execution with roughly
3%-5% higher median wall time on its synthetic workload. That limitation, the
development-release status, and the P95 result above remain relevant when
assessing the upgrade. Neither the waiting CPU fix nor this benchmark proves
an improvement for every arbitrary SQL query.

## Artifacts and reproduction

Raw artifacts remain ignored under `benchmark/results/local/`:

- `20261012_home_upgrade_a_153.json`
- `20261012_home_upgrade_b_2dev.json`
- `20261012_home_upgrade_c_2dev.json`
- `20261012_home_upgrade_d_153.json`
- `20261012_home_2dev_paths.json` and its `.log`
- `20261012_upgrade_2dev_offline_final.log`
- `20261012_home_2dev_integration_final.log`

Reproduce the network comparison in separate environments pinned to each
version, run sequentially in ABBA order, and choose unique output paths:

```sh
python -m benchmark.workloads.http_pool_mixed \
  --output NEW_UNIQUE_RESULT.json --network-label 'Record the current network' \
  --budgets 16 --concurrency 1 32 128 --cache-modes cached \
  --rounds 1 --batches-per-concurrency 2 --no-hooks \
  --receive-mode coordinated --duckdb-threads 4
```

The [development test guide](../../test/README.md) and existing dataset-cache CI
workflow describe regression commands. For the live integration checks:

```sh
DEFEATBETA_RUN_NETWORK_TESTS=1 python -m unittest \
  test.test_duckdb_client.TestDuckDBClientIntegration \
  test.test_all_tickers.TestRepresentativeTickers \
  test.test_ticker_multithreaded -v
```
