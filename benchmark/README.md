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

# All-tickers functional test

`benchmark/all_tickers.py` calls every query operation of the end-to-end
workload, 78 at present, for every US ticker in the catalog (about 10,000). It
checks that calls complete; it does not compare returned values, which the
concurrency comparison does for its eight tickers.

Use **Actions > All-tickers functional test > Run workflow**. A plan job freezes
the catalog, the method list and the dataset version. The tickers are split
into shards (16 by default, at most 20) that run on separate runners at the same
time, each with 4 worker processes. With 16 shards the shards take 40 to 85
minutes, depending on the speed of the runner each one gets, and the final job
takes about 30 minutes more: about 2 hours in all. The final job rechecks errors
on the baseline release and publishes `results.md` as the job summary. Progress files and the report are kept as artifacts for 30 days.

Every call is classified:

- `ok`: the call returned, including an empty result.
- `not_applicable`: the call was not made. News and transcript bodies take the
  latest item of the ticker's news or transcript list; a ticker with an empty
  list has nothing to read.
- `missing_method`: the installed version has no such method. Only a baseline
  release older than the method produces it, and the call is then compared
  like a business error.
- `expected_error`: a `ValueError` raised by `defeatbeta_api` itself, such as
  an unknown industry or missing WACC data.
- `unexpected_error`: any other exception, recorded with its raise site and the
  innermost `defeatbeta_api` frame.
- A ticker that runs longer than 10 minutes is a `timeout`; a worker process
  that exits is `crashed`. Both are replaced and the shard continues.

Every erroring call, and every ticker that timed out or crashed, is rerun in an
isolated install of the baseline release (`release-0.0.62` by default). A call
whose result is worse than in the baseline is a regression and fails the run:
an error where the baseline returned data, or an unexpected error where the
baseline raised a business error. Errors that also occur in the baseline are
listed as pre-existing and do not fail the run. Missing or unrechecked tickers
make the run incomplete.

For a local run over the first tickers of the catalog:

```sh
out=benchmark/results/local/all-tickers
mkdir -p "$out"
python -m benchmark.all_tickers plan --output "$out/plan.json" --limit 20
python -m benchmark.all_tickers run --plan "$out/plan.json" --output "$out/run"
python -m benchmark.all_tickers compare --plan "$out/plan.json" --candidate "$out/run" --output "$out/report"
```

Offline tests: `python -m unittest test.test_all_tickers_harness -v`.
