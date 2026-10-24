# End-to-end concurrency comparison

This harness compares two versions of the product on the complete public query
workload, for example `release-0.0.62` against the current commit. It is a
development measurement; reports stay in GitHub Actions and are not committed.

## Running it

Use **Actions > End-to-end concurrency comparison > Run workflow**. The workflow
compares `release-0.0.62` with the selected commit on one GitHub-hosted runner
and publishes `results.md` as the job summary. Raw evidence is kept as an
artifact for 30 days. See [results](results/README.md) for the latest run.

For a local run, use a new output directory:

```sh
python -m pip install -e . -r benchmark/requirements.txt
python -m benchmark.e2e_concurrency \
  --baseline release-0.0.62 --candidate HEAD \
  --output benchmark/results/local/e2e-concurrency-001
```

Local timings depend on the current network and proxy and must not be compared
directly with GitHub-hosted timings.

## Workload

Discovery freezes every public query operation and its parameters for a fixed
sample of eight tickers: AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA and WMT. The
sample is not statistically representative of the full ticker universe. Excel
export and diagnostic output are excluded; `dcf_data()` is included. News and
transcript wrappers expand into list and body retrieval, and missing source
bodies remain explicit not-applicable tasks. See the
[workload implementation](e2e/README.md).

Each batch runs the complete workload once: currently 8 x 78 = 624 tasks. Worker
counts 1, 4, 16 and 64 divide that fixed work; they do not multiply it.
64 workers match the default connection pool capacity of 16 connections with
up to 4 streams each.

## Method

- Each version is exported into its own source tree and virtual environment.
  Every batch runs in a separate Python process.
- Round 1 starts from an empty disk cache, isolated by version and worker count.
  Round 2 reuses the round 1 cache files of the same version and worker count,
  with fresh memory caches, connections and DuckDB state. A few downloads may
  remain in round 2 and are reported. Do not average the two rounds.
- Version order alternates between worker counts to spread runner drift across
  both versions.
- Batch seconds cover the whole batch, including executor startup, scheduling
  and result materialization. Ticker initialization, output fingerprinting and
  the final pending-download drain are outside batch time; download counters
  include the drain.
- Both versions use the same generous cache budgets rather than their defaults.
- No workload replay, connection warmup, retries or profilers are used.

## Report

`results.md` contains one section per round. Each section has a timing table
with one row per worker count (baseline seconds, candidate seconds, speedup and
calls per second) and a download table listing baseline rows before candidate
rows. Download counters are the five `Ticker.download_data_performance()`
counters as query-phase deltas; shared filesystems are counted once.

Output fingerprints hash column names and every normalized row value, ignoring
row order but keeping duplicate rows. For any task whose fingerprint differs
across batches, the report lists each distinct result per version with the
batches that produced it, so changes within the baseline are not attributed to
the candidate. Failed batches or a dataset change stop the run
while keeping completed evidence.

## Correctness tests

```sh
python -m unittest test.test_e2e_concurrency test.test_e2e_execution test.test_e2e_probe \
  test.test_e2e_benchmark test.test_benchmark -q
python -m pip install -r benchmark/requirements.txt
DEFEATBETA_RUN_BENCHMARK_TLS_TESTS=1 python -m unittest test.test_benchmark.TestBenchmarkTLS test.test_e2e_integration -v
```

The TLS integration suite serves deterministic Parquet data over local HTTP/2
and runs real workers against it, including a second process that reuses the
first process's disk cache. These tests do not assert speed thresholds.
