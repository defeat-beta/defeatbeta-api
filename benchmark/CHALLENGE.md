# DefeatBeta performance challenge

How far can a serverless data lake go with remote Parquet on Hugging Face,
HTTP Range reads, and local DuckDB execution?

Optimize time to a fully materialized result and completion rate for concurrent
calls. Explain the complete path: initialization, metadata, cache, pool admission,
connection setup, transfer, decoding, SQL, and Python materialization. Bandwidth
is one possible limit; latency, CPU, memory, and shared contention can dominate.

Preserve this architecture. Do not substitute a persistent query service,
database server, full local dataset, or precomputed result injection. Changes
inside caching, networking, metadata, planning, and execution remain in scope.

Use the [paired benchmark](README.md) for explicit baseline/candidate comparisons.
Cover every sampled ticker and query operation in cold and all-local-hit states,
with identical work at concurrency 1/4/16/64/128. Fixed-data correctness tests
validate cache behavior; the main report measures current remote public APIs.
Historical network timings are not a universal baseline.

Correct results, recorded defaults, all attempts, and clear timing boundaries
come before speedup claims. Diagnostics explain mechanisms; end-to-end evidence
determines user benefit. Follow the [design](DESIGN.md) and
[report lifecycle](results/README.md).
