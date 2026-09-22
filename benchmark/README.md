# DefeatBeta Performance Challenge

> **How fast can a serverless data lake become?**

## Background

Data lakes are powerful — but they are also intimidating.

If you have ever tried to build one, you probably know the drill:

**S3 → Hive Metastore → Spark → Presto/Trino → Data Catalog → IAM → ...**

Before the first dataset is even queryable, you are already deep inside infrastructure.

But what if you do not need all of that?

What if you are a researcher, an independent developer, or simply a data enthusiast who wants a **simple, free, and maintenance-free way to store and query large datasets**?

This is the idea behind what I call a:

> **Poor Man's Data Lake**

DefeatBeta API is built around this idea.

Its architecture is intentionally simple:

```text
Hugging Face
    │
    │  Parquet over HTTP
    ▼
  DuckDB
    │
    ▼
Application
```

The data is hosted on Hugging Face, the query engine runs locally, and Parquet files are queried directly over HTTP.

There is:

* no database server
* no Spark cluster
* no data warehouse
* no always-on infrastructure to maintain
* almost no hosting cost

Just:

> **Files + HTTP + a query engine**

Simple. Cheap. Serverless.

But simplicity comes with a price:

> **The network is now part of the query engine.**

Remote reads, HTTP latency, metadata access, Parquet layout, data transfer, caching, query planning, and execution can all become bottlenecks.

That leads to the question behind this project:

> **How far can we push this architecture before we hit its fundamental performance limit?**

---

## The Challenge

Use **Systems Engineering + First Principles Thinking** to push DefeatBeta's query performance as far as possible.

For now, the primary benchmark is:

> **Cold Query Latency**

No warm-cache advantage. The goal is to optimize the latency of a real query when the required data is not already available locally.

Explore aggressively. Measure everything. Question every implementation detail.

But there is one fundamental constraint.

---

## Principles

### Do not change the architecture

This is the most important rule.

The architecture must remain:

```text
Remote Parquet on Hugging Face
            +
         HTTP
            +
      Local DuckDB
```

The goal is **not** to make the benchmark fast by turning DefeatBeta into another architecture.

Do not solve the problem by introducing:

* a traditional database server
* a data warehouse
* a Spark/Trino cluster
* a persistent query service
* a separately operated backend
* a full local copy of the dataset

The challenge is to discover how fast the **existing serverless architecture itself** can become.

Everything inside that boundary is open to optimization.

Parquet layout, HTTP behavior, range requests, metadata access, concurrency, caching strategies, prefetching, DuckDB configuration, query planning, indexes, execution strategies, and implementation details can all be challenged.

### Measure, don't guess

Every optimization should be validated by reproducible benchmark results.

The question is not whether an idea sounds faster.

The question is:

> **Did it make the cold query faster?**

### Optimize end to end

Microbenchmarks are useful for understanding bottlenecks, but the final metric is end-to-end query latency.

An optimization only matters if it improves the actual query.

---

The architecture stays.

Everything else is fair game.

**Let's find its limit.**

---

## Benchmark

```
benchmark/
├── README.md                 # Challenge description and benchmark guide
├── config.py                 # Data source, query, and run configuration
├── queries.py                # Fixed query and single cold-query worker
├── bench.py                  # Runner, statistics, and result reporting
├── docs/
│   └── 000_baseline.md        # Baseline record; one document per optimization
└── results/
    ├── summary.md            # Automatically maintained Markdown comparison table
    └── runs/                 # Raw details for each run in Markdown
```

### Running the benchmark

Run these commands from the project root using the existing virtual environment. Install
`httpfs` and `cache_httpfs` before the first run. Extension installation is excluded from
cold-query timing; the runner does not automatically install or update extensions.

```bash
./.venv/bin/python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs'); c.execute('INSTALL cache_httpfs FROM community')"
```

```bash
# Run the baseline or an optimization
./.venv/bin/python benchmark/bench.py --symbol AAPL --runs 3 --tag baseline

# Compare recorded runs
cat benchmark/results/summary.md
```

From the `benchmark/` directory, use:

```bash
../.venv/bin/python bench.py --symbol AAPL --runs 3 --tag baseline
```

The default data commit is pinned to `a46d68650c1f90b7331608350dced8364047b3f7`.
To change the data version, explicitly pass `--revision <40-character-commit-sha>`; `main` is rejected.
Use `--timeout 600` to set the total timeout per worker and `--output <directory>` to select the result directory.
For optimization comparisons, use at least 10 trials and alternate baseline and optimized runs.
Three trials are intended only for an initial assessment.

### Metric definitions

- **Cold Query Latency**: End-to-end time from just before the parent launches the worker until
  the worker fully materializes the DataFrame. Includes process startup, module imports, DuckDB
  initialization, extension loading, network reads, query execution, and result conversion.
  Excludes preflight checks, extension installation, result validation, report writing, and process exit.
- **Cold-cache boundary**: Each trial uses a separate process and a unique empty `cache_httpfs`
  directory, with no query warmup. Its temporary directory is removed afterward. Other applications'
  caches and the OS page cache are left intact. Code pages, DNS, proxy, and remote CDN caches are
  uncontrolled. This measures cold local query data, without claiming a cold machine or remote service.
- **Fixed query**: `SELECT * FROM '<stock_prices_url>' WHERE symbol = ?`, with a bound symbol
  parameter and all matching rows fully materialized. This phase measures the SQL path with the
  current client configuration, excluding `Ticker` initialization and `spec.json` cache validation.
- **Statistics**: Three trials by default; report **median** (primary), min/max, sample standard
  deviation, and individual measurements. Standard deviation is undefined for one sample. An empty
  result, timeout, failure, or inconsistent result marks the run `invalid`; no comparison median is generated.
- **Evidence**: Each run's Markdown embeds a complete JSON report with configuration, versions,
  extension binary and script SHA-256 hashes, timing breakdowns, CPU time, peak RSS, cache directories
  and file sizes, row counts, and a result checksum independent of row order. Cache file size is not
  HTTP download volume. No additional diagnostic profiling was enabled for this baseline.

### Optimization records

See [000_baseline.md](docs/000_baseline.md) for the baseline and [summary.md](results/summary.md)
for recorded runs. For each optimization, add `docs/NNN_<name>.md` covering the hypothesis, changes,
reproduction commands, environment and data versions, raw baseline and optimized results, result
consistency, absolute latency change, percentage improvement, limitations, and conclusion.
Keep records even when an optimization provides no improvement.

Percentage improvement is `(baseline_median - optimized_median) / baseline_median × 100%`.
Compare only valid runs with matching data, symbol, results, and environment. Small changes under
variable network conditions require additional samples to validate.
