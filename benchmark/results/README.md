# Benchmark records and reports

## Local iteration and publication

The benchmark uses an explicit two-stage workflow:

1. Run `bench.py run` as many times as needed while developing an optimization.
   Each invocation writes one ignored JSON record under `local/`; it does not
   create a Markdown report or a tracked archive.
2. After selecting satisfactory baseline and candidate runs, invoke
   `bench.py archive` explicitly. Archiving validates and combines those exact
   records into one tracked comparison JSON and one Markdown report without
   rerunning the benchmark.

Local execution is unlimited, while storage is intentionally bounded: the
newest 100 records from the last 30 days are retained. Use
`--baseline-source` and `--candidate-source` to select the exact runs that
should become durable evidence. Archives are created exclusively and are never
silently replaced.

## Storage layout

- `local/<run-id>.json`: one file per invocation, ignored by Git. Completed runs retain the newest 100 within 30 days. Cleanup runs after each benchmark; recent unfinished runs are protected, and unfinished records older than 30 days expire.
- `archive/NNN_<name>.json`: one immutable paired baseline/candidate record for a published optimization.
- `archive/NNN_<name>.md`: the single generated comparison report for that optimization.

Run from the project root (one file per invocation, unlimited runs):

```bash
./.venv/bin/python benchmark/benchmark.py run \
  --runs 3 \
  --tag <attempt-tag> \
  --http-proxy http://127.0.0.1:8118
```

Publish one satisfying comparison from the project root (archiving does not run queries):

```bash
./.venv/bin/python benchmark/benchmark.py archive \
  --baseline-source benchmark/results/local/<baseline-run-id>.json \
  --candidate-source benchmark/results/local/<candidate-run-id>.json \
  --name 001_connection_reuse
```

If the candidate intentionally changes a configured setting, declare each one
with `--allow-setting-difference <name>`. Undeclared differences, mismatched
environments, revisions, symbols, or result hashes reject publication.

The executable benchmark calls `Ticker(symbol).price()` through the real
`defeatbeta_api` package. Its primary metric is the time emitted by
`DuckDBClient._execute_query`; package import, client initialization, the full
API call, cache state, and cache_httpfs diagnostics are recorded separately.

Local run JSON uses format version 2 with deduplicated `shared` entries. Paired
comparison archives use format version 3 and embed the exact version 2 baseline
and candidate records. `000_baseline` and `001_resolve_once_cdn` are legacy
archives produced by the retired direct-DuckDB benchmark and remain readable
by `report.py`.
