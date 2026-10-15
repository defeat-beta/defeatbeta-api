# End-to-end workload implementation

This package defines the single workload used by the
[main benchmark](../README.md). The [design](../DESIGN.md) specifies timing,
cache states, correctness checks, and report lifecycle.

| Module | Responsibility |
| --- | --- |
| `plan.py` | Discover every query operation, freeze parameters and sample tickers, build the complete Cartesian workload and twelve phases. |
| `backend.py` | Prepare isolated real product caches, discover body identifiers, record data identity, and observe cache misses. |
| `execution.py` | Materialize public API calls, time them, warm exact tasks, distribute identical work, and retain every outcome. |

The fixed sample is AAPL, JPM, XOM, O, PDD, NVO, ARM, and CRWV. It retains
financial/nonfinancial, non-US, recent-listing, and currency paths; it is not a
statistically representative sample of the full ticker universe. Missing sample
tickers fail discovery instead of being silently replaced. No operation is
removed because it is slow or fails.

The initial sixteen-symbol
[GitHub calibration](https://github.com/defeat-beta/defeatbeta-api/actions/runs/38715579086)
exhausted its 30-minute budget after cold latency and a partial cached phase.
The sample size was reduced while retaining coverage differences and observed
failing tickers. The temporary calibration command and workflow are retired.
Further measurements use the main CLI and per-phase GitHub jobs.

Correctness tests cover new API discovery, frozen arguments, complete ledgers,
all-hit preparation, timing boundaries, partial outcomes, and real Parquet cache
integration. Official performance timings come from GitHub, not workstation runs.
