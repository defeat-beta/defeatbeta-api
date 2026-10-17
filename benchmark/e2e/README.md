# End-to-end workload implementation

This package defines the single workload used by the
[main benchmark](../README.md). The [design](../DESIGN.md) specifies timing,
cache states, correctness checks, and report lifecycle.

| Module | Responsibility |
| --- | --- |
| `plan.py` | Discover every query operation, freeze parameters and sample tickers, build the complete Cartesian workload and twelve phases. |
| `backend.py` | Prepare isolated real product caches, discover body identifiers, record data identity, and observe cache misses. |
| `cache.py` | Prepare complete native cache seeds, validate coverage and checksums, and restore isolated active caches. |
| `execution.py` | Materialize public API calls, time them, warm exact tasks, distribute identical work, and retain every outcome. |

The fixed sample is AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, and WMT. These
well-known issuers were explicitly selected by the maintainer after a query
availability check, not a performance ranking. On the 2026-10-15 dataset, all
624 ticker/operation calls completed without exceptions; five returned empty
tables. Empty results remain valid outcomes. This preflight is not performance
evidence or a guarantee about future data availability.

The sample is not statistically representative of the full ticker universe.
Missing sample tickers fail discovery instead of being silently replaced, and
later runs retain unexpected failures. No query operation is removed. Changing
the sample changes the workload identity; earlier cohorts' absolute timings
cannot be used as a comparison for this cohort.

The initial sixteen-symbol
[GitHub calibration](https://github.com/defeat-beta/defeatbeta-api/actions/runs/38715579086)
exhausted its 30-minute budget after cold latency and a partial cached phase.
The sample size was first reduced to eight and subsequently replaced by the
current maintainer-approved list. The temporary calibration command and workflow
are retired. Further measurements use the main CLI and per-phase GitHub jobs.

Correctness tests cover new API discovery, frozen arguments, complete ledgers,
complete-file cache preparation using the measurement concurrency, timing boundaries,
partial outcomes, and real Parquet cache integration. A changing-read-footprint
fixture covers a zero-request replay followed by a previously unseen byte range.
Complete seed coverage makes that range local too. One exact-work warmup records
a complete task ledger and must have zero requests. Formal measurement is never
retried to replace a cache miss. Tests reject coverage gaps, corrupt blocks,
insufficient disk space, identity changes, and shared mutable metadata. Optional
released-source integration verifies the original 0.0.62/DuckDB 1.5.3 environment.
Official performance timings come from GitHub, not workstation runs.
