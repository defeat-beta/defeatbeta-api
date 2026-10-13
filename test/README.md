# Development tests

The paired benchmark has offline reporting/publication checks and an opt-in
real TLS integration suite:

```sh
python -m unittest test.test_benchmark test.test_benchmark_publication -q
python -m pip install -r benchmark/requirements.txt
DEFEATBETA_RUN_BENCHMARK_TLS_TESTS=1 python -m unittest test.test_benchmark.TestBenchmarkTLS -v
```

TLS integration generates deterministic data and checks HTTP/2, HTTP/1.1,
Range responses, and four cache states with isolated workers. It uses loopback
sockets and OpenSSL without the public service; Linux CI runs it explicitly.
Report checks reject incomplete/duplicate samples, nonfinite timings, result
mismatches, mixed source/workflow identities, short publication samples, missing
evidence, and replacement of an existing archive. See the
[benchmark guide](../benchmark/README.md) for performance measurements; these
correctness tests do not assert hardware-dependent speed thresholds.

Run the offline cache, shared-resource and benchmark regressions from the
repository root:

```sh
python -m unittest test.test_dataset_cache_fs test.test_resolve_direct test.test_benchmark test.test_duckdb_client.TestDuckDBClient test.test_test_collection test.test_shared_resources test.test_http_pool test.test_http_runtime test.test_shared_query_benchmark -q
```

These regressions include concurrent thread/process cache tests and loopback
HTTP/1.1 tests for direct/proxy connection reopening and slow-proxy fallback.
Verified TLS HTTP/2 fixtures exercise connection sharing, idle GOAWAY and
concurrent recovery. Pool regressions additionally cover atomic reservations,
global budgets across routes/origins, cold-start coordination, dynamic SETTINGS
reductions, streaming response ownership, queue timeouts, and idle shrinkage.
They bind random ports on `127.0.0.1` without requiring
internet access. The HTTP/2 fixture requires an `openssl` executable.

The `dataset-cache` GitHub workflow runs offline regressions on Linux, macOS and
Windows. Its manual network-smoke job additionally checks direct Hugging Face
HTTP/2 Range reads and live queries on all three platforms.
The complete offline module list is in the
[workflow](../.github/workflows/dataset-cache.yml). Packet-capture helper tests
use Unix process UIDs and run in a separate non-Windows step; they mock capture
and do not request administrator privileges.

The exhaustive ticker sweep does not run during test discovery. A small live
price sample is opt-in with `DEFEATBETA_RUN_NETWORK_TESTS=1`; the full US ticker
price sweep is opt-in with `DEFEATBETA_RUN_ALL_TICKERS=1`. Set
`DEFEATBETA_TEST_HTTP_PROXY` only if the test network needs an explicit proxy.

The Excel formula verification in `TestTicker.test_dcf` is opt-in with
`DEFEATBETA_RUN_EXCEL_TESTS=1` because it launches Excel. SiliconFlow transcript
integration tests are opt-in with `DEFEATBETA_RUN_AI_TESTS=1` and require
`test/siliconflow_api.key`.

Use `pytest -s` to show DEBUG output; pytest otherwise captures output from
passing tests. See [the shared-resource engineering report](../benchmark/reports/SHARED_RESOURCES.md)
for benchmark methodology and acceptance cases.

The offline DuckDB waiting reproducer has separate correctness checks:

```sh
python -m unittest test.test_duckdb_wait_repro -v
```

These checks use synthetic Parquet data and a gated fsspec reader in disposable
processes. They cover blocked reads, concurrent results, cancellation, cursor
recovery, and process deadline cleanup. CPU ratios are reported by
`python -m benchmark.diagnostics.duckdb_wait_repro --output NEW_UNIQUE_RESULT.json`; CI does
not assert machine-dependent CPU thresholds.

Thread ownership is diagnostic data, not an API guarantee: DuckDB 2.0 may use
a different thread even with `threads=1`. Tests check the effective cursor
setting and observable results instead. The shared-client shutdown regression
uses a separate interpreter to verify automatic close and absence of native
binding leak warnings, with no network access.

The compute-only thread comparison uses an in-memory aggregate and an
independent integer reference. Its correctness and process-cleanup tests run
with `python -m unittest test.test_duckdb_cpu_comparison -v`. Use
`python -m benchmark.diagnostics.duckdb_cpu_comparison --output NEW_UNIQUE_CPU_RESULT.json`
to measure the cost of reducing intra-query parallelism. The public-network
mixed-API benchmark accepts `--duckdb-threads 1` or `--duckdb-threads 4` as
diagnostic controls; these do not change product defaults. Compare reports
only when dataset versions, result fingerprints and all other policies match.

Version-resolution regressions cover equal-size and changed-size remote objects,
actual byte reads with disk caching enabled and disabled, delayed old-generation
resolutions, shared signed-URL refresh, and route changes. Footer-lock regressions
cover stable lock identity across daily versions, Windows contention retries,
unrelated lock errors, and unlock after a preparation error. A spawned-process
test holds a real OS lock for more than ten seconds, terminates its owner, and
checks that the waiting process acquires and releases the same lock. The Windows
branch unit tests use a simulated CRT; the spawned test uses the host OS and must
also run on Windows CI to validate native Windows behavior.

On 2026-10-13, the full offline suite ran 377 tests in 42.952 seconds on macOS
arm64: 376 passed and one optional public-network test was skipped. This includes
eight added resolution and lock regressions. Four live integration tests then
passed in 26.382 seconds on the office network, with dataset metadata reporting
`2026-10-12T05:39:55Z` and no native binding or atexit warnings. These are
correctness checks, not a throughput comparison with the home-network benchmark.
Linux and Windows runtime validation was still pending at that stage. Local logs are retained
under the ignored `benchmark/results/local/` directory as
`20261013_review_fixes_offline.log` and
`20261013_office_review_fixes_integration.log`.

After the script layout migration on the same date, the expanded local offline
suite ran 393 tests in 44.459 seconds: 392 passed and one optional public-network
test was skipped. It additionally includes the existing CDN lifetime and Unix
packet diagnostic tests. The log is `20261013_benchmark_layout_offline.log`.
All twelve CLI help entries passed, and minimal executions of the relocated
DuckDB waiting, DuckDB compute, and HTTP/2 stream probes completed successfully.
Mixed-query source-fingerprint paths were checked offline with no queries.

The subsequent generation-consistency review added ten offline regressions.
Real DuckDB queries pause during data reads while another caller updates the
dataset. Equal-size and changed-size Parquet objects are checked with disk
caching enabled and disabled against a complete-file reference. Other cases
cover post-materialization validation, bounded whole-query retries, unchanged
query errors, concurrent SQL execution, expired paths, and rejection of in-flight
single-range and split-range cache publication. Shared-cache tests gate success
and failure publication and verify that an old owner cannot remove a newer build.
The expanded suite ran 403 tests in 43.271 seconds on macOS arm64: 402 passed and
one optional public-network test was skipped. No public-network benchmark was
run for these correctness fixes.

Final live acceptance on 2026-10-13 ran five checks in 121.520 seconds. Four
passed: the isolated-cache price/transcript query, representative ticker prices,
parallel market-capitalization queries, and concurrent same-ticker profile
queries. Metadata reported `2026-10-12T05:39:55Z`. The forced-direct HTTP/2 smoke
check failed while establishing TCP to huggingface.co, before CDN resolution.
An independent curl check also timed out before TCP establishment with proxy
use disabled; curl using the configured route returned HTTP 302 in 0.718 seconds.
This records a direct-route connectivity failure, not a passing direct-CDN test.
The raw log is retained locally as
`benchmark/results/local/20261013_final_acceptance_live.log`.
At that stage, the latest available GitHub run covered an older commit, so native
Linux and Windows acceptance for the local revision was still pending. These live
checks are correctness checks and are not a bandwidth or latency benchmark.

## Main acceptance, 2026-10-13

The refactor was committed directly to `main` as `81e69be`. Native CI exposed
diagnostic timing assumptions that the initial macOS run did not detect:

- TCP can deliver two server writes as one application chunk. The connection
  timeline test now verifies ordering and payload preservation on a coalesced
  response; controlled single-chunk and multiple-chunk inputs verify exact
  delivery timestamps independently of OS buffering.
- Short measurements can be quantized by the Windows monotonic clock. Both
  CPU comparison and waiting-reproducer measurements now use `perf_counter`.
  A zero measured interval preserves results and records a null rate or ratio;
  the waiting CLI displays an unavailable ratio as `n/a`.

The diagnostic fixes were committed as `c228257` and `7f8ace5`. Regression cases
reproduced the failures before each fix, including a coarse deadline clock,
zero elapsed measurements, and CLI output for an unavailable ratio. Fourteen
connection-timeline/CPU-comparison tests and seven waiting-reproducer tests
passed locally. Product query and connection-pool code did not change during
these CI fixes.

Code revision `7f8ace5` passed both the
[automatic native regression run](https://github.com/defeat-beta/defeatbeta-api/actions/runs/38339655344)
and the [complete manual acceptance run](https://github.com/defeat-beta/defeatbeta-api/actions/runs/38339704947):

| Runner | Offline regressions | Live network smoke |
| --- | --- | --- |
| Linux (`ubuntu-latest`) | Passed | Passed |
| macOS (`macos-latest`) | Passed | Passed |
| Windows (`windows-latest`) | Passed | Passed |

Live smoke includes direct verified HTTP/2 Range reads, isolated-cache price and
transcript queries, representative ticker prices, concurrent market-capitalization
queries, and same-ticker profile concurrency. Optional offline skips remain
intentional. This validates correctness and native runtime compatibility;
it does not establish a universal throughput optimum. No package release was
created by the acceptance workflow.
