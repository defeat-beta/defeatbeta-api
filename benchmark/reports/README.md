# Engineering report archive

These reports preserve the investigation that produced the shared connection
pool, footer/index reuse, HTTP/2 receive coordination, and DuckDB waiting fix.
They describe the code and network conditions at the time of each experiment.
An earlier report's "current", "final", or "unresolved" statement is local to
that report, not a claim about the present implementation.

Reproduction commands and source references use the categorized `workloads`
and `diagnostics` module paths. Historical measurements and recorded hashes
remain unchanged; a run of the relocated code will have new source hashes.

For current behavior, use [HTTP connection pool](../../doc/api/HTTP_Connection_Pool.md)
and [Local file cache](../../doc/api/Local_File_Cache.md). For tools and publication
rules, return to the [benchmark guide](../README.md). Historical local JSON/log
filenames are provenance references; most are ignored and unavailable in a
fresh checkout. Public result archives are listed under [results](../results/README.md).

## Current recorded status

The current allocator uses four retained core connections per origin/route,
sixteen total connections, a four-stream client ceiling, and up to four parallel
initializations after the first connection establishes capacity. Connections
grow on demand; there is no periodic HTTP heartbeat. HTTP/2 receive coordination
and the official pinned DuckDB `2.0.0.dev2610011535` waiting fix are implemented.
The latter is a development build, not a stable DuckDB 2.0 release.

The [DuckDB upgrade validation](DUCKDB_2_UPGRADE.md) is the latest retained
engine comparison. It reports lower batch elapsed time and CPU in its tested
home-network workloads, alongside a higher 128-query P95 and a small synthetic
compute regression. It does not establish improvement for every query or
bandwidth saturation.

The October 13 correctness follow-up fixed version-aware CDN resolution,
late old-generation results, cross-process lock waiting, and daily footer-lock
accumulation. On macOS arm64, 376 offline tests passed and one optional network
test was skipped; four office-network integration tests passed. Native Linux
and Windows validation remains pending. See the [test guide](../../test/README.md)
for coverage and local log names. These checks are not a new performance baseline.

## Sharing and allocation

| Report | Role and follow-up |
| --- | --- |
| [Shared resources](SHARED_RESOURCES.md) | Initial transport, footer, and index sharing; its early capacity policy was replaced by the configurable allocator. |
| [HTTP pool](HTTP_POOL.md) | Allocator design, protocol-thread correction, and early default selection. |
| [Mixed API capacity](HTTP_POOL_MIXED.md) | Cached/uncached concurrency and budgets on the in-car network. |
| [Scheduler review](HTTP_POOL_SCHEDULER.md) | Demand-driven parallel initialization, scheduling, and lifecycle fixes; subsequent latency work appears below. |

## Request and receive timing

| Report | Role and follow-up |
| --- | --- |
| [Latency findings](LATENCY_FINDINGS.md) | Initial query-time attribution and reuse questions. |
| [Connection timeline](CONNECTION_TIMELINE.md) | Connection/request phase instrumentation and observations. |
| [Cache pipeline](CACHE_PIPELINE.md) | Worker admission, bridge, network, publication, and instrumentation overhead. |
| [Ready HTTP/2 streams](HTTP2_READY_STREAMS.md) | Reproduction of decoded data delayed behind another receive. |
| [Receive coordination](HTTP2_RECEIVE_COORDINATION.md) | The project's receive-notification fix and validation. |
| [Office validation](HTTP2_OFFICE_VALIDATION.md) | Office-network follow-up after receive coordination. |
| [Office CPU diagnosis](HTTP2_OFFICE_CPU_DIAGNOSIS.md) | Native waiting investigation leading to the isolated DuckDB reproducer. |

## DuckDB waiting and upgrade

| Report | Role and follow-up |
| --- | --- |
| [Waiting reproduction](DUCKDB_WAIT_REPRO.md) | Offline delayed-read CPU reproduction, cancellation, and recovery checks. |
| [Execution comparison](DUCKDB_EXECUTION_COMPARISON.md) | Evaluation of caller-only execution and its compute tradeoff; the default retains parallel execution. |
| [Upstream fix evaluation](DUCKDB_UPSTREAM_WAIT_FIX.md) | Official candidate provenance and isolated compatibility checks. |
| [Upgrade validation](DUCKDB_2_UPGRADE.md) | Adopted development build, exit cleanup, live comparison, and remaining validation limits. |

## Connection lifetime

| Report | Role and follow-up |
| --- | --- |
| [Idle CDN connection](CDN_IDLE.md) | Observed HTTP session retirement without business traffic. |
| [Active CDN connection](CDN_ACTIVE.md) | Ten-minute experiment with periodic real one-byte requests; diagnostic traffic only. |
| [TCP keepalive capture](TCP_KEEPALIVE_CAPTURE.md) | Distinguishes TCP responsiveness from HTTP session eligibility. |

These lifetime observations informed on-demand recovery. They do not establish
a universal server idle timeout or justify background HTTP traffic in production.
