# Benchmarks and performance diagnostics

This directory contains developer tools for measuring query latency, explaining
network waits, and reproducing concurrency problems. For application behavior
and configuration, start with [Local file cache](../doc/api/Local_File_Cache.md)
and [HTTP connection pool](../doc/api/HTTP_Connection_Pool.md).

The original [performance challenge](CHALLENGE.md) explains the project's goals
and constraints. The [test guide](../test/README.md) lists correctness regressions.

## Directory guide

| Location | Purpose |
| --- | --- |
| `benchmark.py`, `report.py` | Main query benchmark and explicit result publication. |
| [workloads/](workloads/) | Query concurrency, sharing, default-policy, and connection-capacity comparisons. |
| [diagnostics/](diagnostics/) | Timing instrumentation, connection lifetime probes, and controlled reproductions. |
| [reports/](reports/README.md) | Historical investigations, conclusions, and follow-up links. |
| [results/archive/](results/README.md) | Explicitly archived comparisons or release records, paired with JSON evidence. |
| `results/local/` | Ignored local runs, logs, traces, and temporary measurements. |

Reusable tools and curated engineering reports belong in the source repository.
Several diagnostic modules are imported by regression tests, so they must be
available in a source checkout. Run the categorized modules with `python -m`
from the repository root, as shown below. They are developer tooling, not a
supported application API; package discovery includes only `defeatbeta_api*`.
The main `benchmark.py` and `report.py` entry points and result directories
retain their original paths. The categorized tools have no old-path aliases.

Raw local runs are not published automatically. Engineering reports refer to
some local artifacts that are not part of a checkout; those reports preserve
methods and historical observations, not complete release archives. Only
explicitly selected evidence belongs in `results/archive/`.

## Start here

Run commands from the repository root in the project's installed environment.
Choose a new output filename for each diagnostic run.

**End-to-end cold query latency:**

```sh
python benchmark/benchmark.py run --runs 3 --tag cold_price --api-method price
```

This uses isolated cold samples and writes local records. See the
[record and publication workflow](results/README.md) for paired comparisons,
release snapshots, and archiving selected results.

**Concurrent mixed Ticker APIs with the current connection budget:**

```sh
python -m benchmark.workloads.http_pool_mixed \
  --output benchmark/results/local/mixed_queries.json \
  --network-label "Office network" \
  --budgets 16 --concurrency 1 32 128 \
  --cache-modes cached uncached --rounds 2
```

Use a label describing the actual network. This benchmark prepares metadata,
clears data extents between measured batches, and checks result fingerprints.
Its timing boundary differs from a completely cold client. Diagnostic flags
are experimental controls and do not prescribe application configuration.

**Offline waiting and compute controls:**

```sh
python -m benchmark.diagnostics.duckdb_wait_repro \
  --output benchmark/results/local/duckdb_wait.json
python -m benchmark.diagnostics.duckdb_cpu_comparison \
  --output benchmark/results/local/duckdb_compute.json
```

These isolate delayed reads and CPU work. They complement real-query results;
they do not establish internet throughput.

## Tool inventory

| Tool | Use |
| --- | --- |
| [benchmark.py](benchmark.py), [report.py](report.py) | Cold queries, symbol sequences, Range experiments, and validated result archives. |
| [http_pool_mixed.py](workloads/http_pool_mixed.py) | Concurrent mixed APIs, cached/uncached paths, pool limits, and optional detailed traces. |
| [http_pool_defaults.py](workloads/http_pool_defaults.py) | Controlled comparisons of core connections, fetch workers, and stream ceilings. |
| [pool_capacity_benchmark.py](workloads/pool_capacity_benchmark.py) | Loopback HTTP/1.1 admission and queueing control. |
| [connection_timeline.py](diagnostics/connection_timeline.py) | Connection, handshake, socket, and request timing; also shared instrumentation. |
| [cache_pipeline.py](diagnostics/cache_pipeline.py), [cache_timeline.py](diagnostics/cache_timeline.py) | Cache-worker, protocol-bridge, publication, and query timing. |
| [http2_stream_probe.py](diagnostics/http2_stream_probe.py), [http2_stream_timeline.py](diagnostics/http2_stream_timeline.py) | Reproduce and trace decoded HTTP/2 data waiting for consumer delivery. |
| [duckdb_wait_repro.py](diagnostics/duckdb_wait_repro.py) | Held-read waiting, cancellation, and cursor recovery in disposable processes. |
| [duckdb_cpu_comparison.py](diagnostics/duckdb_cpu_comparison.py) | Compute-only comparison with an independent result reference. |
| [cdn_idle.py](diagnostics/cdn_idle.py), [cdn_active.py](diagnostics/cdn_active.py) | CDN idle retirement and lifetime under real request traffic. |
| [tcp_keepalive_capture.py](diagnostics/tcp_keepalive_capture.py) | Explicit OS socket and packet diagnostics; capture may require OS privileges. |
| [shared_query_benchmark.py](workloads/shared_query_benchmark.py) | Earlier sharing comparison and common helpers. Its baseline loader reads selected modules from the checkout's `HEAD`, not a permanently fixed release. |

CLI tools expose their arguments with `--help`; timeline helper modules are
also imported by tools and tests. Network diagnostics generate real downloads,
and detailed instrumentation adds overhead. Keep traced diagnosis separate
from minimally instrumented performance comparisons.

## Interpreting and publishing results

Record the source revision, dependency versions, dataset version, network route,
cache/connection preparation, workload, and timing boundary. Compare matched
result fingerprints before interpreting timing differences. Daily dataset
updates and network changes can invalidate an otherwise similar comparison.

Report latency distributions, CPU use, downloaded bytes, failures, and pool
waiting together. Application bytes divided by elapsed time is not wire
bandwidth or proof of link saturation. Historical home, office, and in-car
runs must not be pooled into a single speedup claim.

For contributions, include the reusable tool, relevant regression coverage,
and a concise interpretation with its limitations. Keep exploratory logs and
machine-specific captures in `results/local/`; select durable public evidence
explicitly using the [archive workflow](results/README.md). The
[report index](reports/README.md) identifies historical investigations and the
latest recorded validation without requiring application users to read them all.
