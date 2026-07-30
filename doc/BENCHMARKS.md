# Benchmarks

Defeat Beta queries remote Parquet files, so performance varies with network location,
cache state, selected columns, predicates, and dataset size. A single "queries are
sub-second" claim would hide the most important distinction: the first remote read and
a repeated cached query behave very differently.

## Reference Result

The following result was observed on July 30, 2026:

| Item | Value |
| --- | --- |
| Machine | Apple M1 Pro, 10 CPU cores, 16 GB memory |
| Operating system | macOS 26.5.2 |
| Python | 3.11 |
| Package | defeatbeta-api 0.0.60 |
| DuckDB | 1.5.3 |
| Query | `Ticker("AAPL").price()` |
| Result size | 7,967 rows |

| Cache state | Observed wall time |
| --- | ---: |
| Empty cache, including validation and remote fetch | 14.13 s |
| Valid on-disk cache in a new Python process | 3.88 s |
| Repeated query in the same Python process | 0.009 s |

These numbers are an illustrative observation, not a service-level guarantee. In
particular, the empty-cache result includes network transfer and cache refresh work.

## Reproduce the Query

Create a fresh Python 3.11 environment, install the package, and run:

```python
from time import perf_counter

from defeatbeta_api.data.ticker import Ticker

start = perf_counter()
ticker = Ticker("AAPL")
initialized = perf_counter()

first = ticker.price()
after_first = perf_counter()

second = ticker.price()
after_second = perf_counter()

print(f"initialization: {initialized - start:.3f}s")
print(f"first query:    {after_first - initialized:.3f}s")
print(f"second query:   {after_second - after_first:.3f}s")
print(f"rows:           {len(second):,}")
```

Run the script in a second process to measure reuse of the on-disk block cache. The
cache is validated against the remote dataset timestamp during client initialization.

## Interpreting Results

- **First use:** expect extension setup, metadata access, and remote Parquet reads.
- **Cross-process reuse:** downloaded blocks can be reused, but Python imports,
  DuckDB initialization, and query planning still occur.
- **Same-process reuse:** repeated query execution can reuse both the initialized
  client and local cached blocks.
- **Dataset refresh:** when the published `spec.json` timestamp changes, stale cached
  data is invalidated before the next query.
