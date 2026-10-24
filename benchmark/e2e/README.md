# End-to-end workload implementation

This package defines the workload used by the
[concurrency comparison](../README.md).

| Module | Responsibility |
| --- | --- |
| `plan.py` | Discover every query operation, freeze parameters and sample tickers, and build the complete Cartesian workload. |
| `backend.py` | Prepare isolated real product caches, discover body identifiers, record data identity, and observe cache counters. |
| `probe.py` | Retain bounded logical range traces, exact request counters, and redacted original exceptions without changing requests. |
| `execution.py` | Materialize public API calls, distribute identical work to N workers in one timed pass, and retain every outcome. |

The fixed sample is AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA and WMT. These
well-known issuers were selected by the maintainer after a query availability
check, not a performance ranking. Empty results remain valid outcomes.

Missing sample tickers fail discovery instead of being silently replaced. No
query operation is removed, and a new public query method is covered
automatically. Changing the sample changes the workload identity; timings from
different workloads cannot be compared.
