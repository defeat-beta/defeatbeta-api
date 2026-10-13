# Shared transport and Parquet metadata refactor

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

This report preserves the October 9 implementation and measurements. The
current configurable allocator and default-policy evidence are documented in
[HTTP pool engineering](HTTP_POOL.md).

## Scope

This refactor shares network transports, validated Parquet footers and immutable
parsed indexes across Tickers and independently configured DuckDB clients.
It adds no public connection-capacity or heartbeat settings. It does not attempt
to prove bandwidth saturation or replace the HTTP/TLS/TCP protocol stacks.

The comparison baseline is release 0.0.62, commit
`897e9a76fe50e5c929473de4197e97435dd0190b`. Live measurements below were collected
on October 9, 2026, in the current company network, with existing environment
proxy routing preserved. They must not be treated as measurements of the home
network or as a fixed throughput target for other networks.

## Ownership and request path

```text
Ticker / DuckDBClient
  -> shared dataset spec and CDN-resolution caches
  -> cached or uncached registered filesystem
  -> SharedHttpClient handle
  -> process registry selected by effective proxy and TLS trust identity
  -> HTTPX / httpcore origin-specific HTTP/2 or HTTP/1.1 connections
  -> TLS -> OS TCP -> existing proxy route or direct origin
```

Metadata GET/HEAD and data Range GET use the same transport registry. Timeout
policy belongs to each request, rather than to the first owner creating a pool.
Closing one owner closes only its handles. Active borrowers protect a pool from
registry eviction; at most 16 routing identities are retained. If every identity
is active, creation of another identity fails with a bounded pool error.

There is no startup one-byte prewarm or periodic network activity. Business
requests reuse eligible connections. OS TCP keepalive is enabled with
`SO_KEEPALIVE` and retains OS timer defaults. HTTPX/httpcore handles HTTP/2
GOAWAY state and replacement connections; dataset GET retries are bounded.
Idle retirement is discovered and recovered when the next business request
arrives. Explicit and environment proxies remain supported; CDN URL resolution
does not override them. Signed URL refresh is coalesced by generation.

Supported dataset queries continue through the shared HTTPX range transport
when local caching is disabled or fails. Other DuckDB sources retain their
native reader. The existing native HTTP settings remain available for that
reader, as documented in `doc/api/Advanced_Usage.md`.

## Footer and index lifecycle

- Footer identity includes file/version, total size and canonical spec footer
  hints. Index identity adds the footer hash, DuckDB version and index format.
- Process-wide single-flight preparation lets sequential or concurrent Tickers
  reuse one result. A failed owner releases all waiters and permits a later retry.
- Per-file interprocess locks serialize footer preparation in a shared directory;
  publication is atomic. A fresh process reads a validated disk footer without
  downloading it again. Different cache directories share footer bytes within a
  process and publish their own disk copies.
- Footer and parsed-index shared caches each have a 32 MiB / 256-entry bound.
  Index accounting includes Python row/container overhead. Local clients hold
  weak index references, allowing evicted indexes to be reclaimed.
- Footer reads preserve `st_mtime`; data blocks still update their timestamps
  for disk eviction order. Version changes, changed spec hashes, missing files
  and detected corruption invalidate the relevant retained entries.
- Reuse depends on valid, retained entries. It is not an exactly-once download
  promise across eviction, corruption, version changes or separate directories
  in different processes. Connections and parsed indexes are process-local.

## Protocol evidence informing the design

Earlier controlled CDN observations found TCP keepalive ACKs after an idle
HTTP/2 GOAWAY at approximately 60 seconds. TCP responsiveness therefore did not
mean the HTTP session remained eligible for new requests.

A separate ten-minute run with one-byte business GETs every ten seconds completed
61 requests over one TCP/TLS connection, using stream IDs 1 through 121 with no
observed GOAWAY. The two runs reached different CDN addresses; neither establishes
a universal retirement timeout or proves the server's precise timeout policy.
The one-byte traffic belongs only to the diagnostic experiment, not production.
See `CDN_ACTIVE.md`, `CDN_IDLE.md` and `TCP_KEEPALIVE_CAPTURE.md` for reproduction.

## Live query benchmark

Run each case in a separate process, without other benchmark/test workloads:

```bash
python -m benchmark.workloads.shared_query_benchmark --baseline --output baseline.json
python -m benchmark.workloads.shared_query_benchmark --capacity 16 --output candidate.json
python -m benchmark.workloads.pool_capacity_benchmark --output pool-capacity.json
```

`--capacity` is a diagnostic script option, not a product setting. The baseline
loader selects the three original production modules from Git before importing
product code and records their hashes. Every run uses an isolated disk cache.
DuckDB's additional external-file cache is disabled, pending prefetch is drained,
and data memory/disk extents are cleared before each cold batch. Footer/index
state and connections are retained. Fingerprints are computed outside timing.

Two valid baseline runs and two capacity-16 runs used dataset version
`2026-10-09T05:15:33Z`. Result fingerprints matched for initialization, all price
batches and mixed APIs. Final loaded production source hashes matched the working
tree. Each cold price batch below contains N distinct Tickers queried with N
workers; values are batch wall seconds, not per-Ticker latency.

| Tickers / workers | Baseline runs | Capacity-16 runs | Final run |
| --- | --- | --- | --- |
| 1 | 1.254-1.819 | 1.073-1.083 | 1.083 |
| 2 | 2.257-3.442 | 2.045-2.111 | 2.111 |
| 4 | 3.847-6.202 | 3.374-3.375 | 3.375 |
| 8 | 16.676-27.704 | 6.985-7.370 | 7.370 |
| 16 | 17.424-35.087 | 16.705-18.047 | 16.705 |
| 32 | 31.376-59.976 | 30.611-33.322 | 33.322 |

The baseline constructor took 2.343-3.513 seconds and the final candidate took
1.273 seconds. The first price call alone took 2.504-2.779 seconds in the baseline
and 3.465 seconds in the final candidate; connection setup moved out of startup.
Constructor plus first price took 5.121-6.017 seconds versus 4.738 seconds.

The strongest repeatable sharing result is preparation in two independent
DuckDB clients: baseline 2.430-3.015 seconds per client with eight extra GET/HEAD
requests in total; final candidate 0.030 and 0.017 seconds with zero extra GET/HEAD.
Controlled tests independently verify single download/parse under concurrency.

Hot queries download zero bytes. At 16 workers, baseline hot batch wall time was
0.191-0.210 seconds and candidate time was 0.238-0.278 seconds. Mixed-file wall
time was 4.947-6.300 seconds versus 5.331-5.339 seconds. These measurements do not
support a claim that every scenario gets faster. The runs are small samples and
network/CPU variation is substantial; raw phase ratios do not establish causality.

The final cold batches recorded 1.10 / 2.70 / 4.78 / 10.58 / 22.59 / 44.93 MB
downloaded for 1 / 2 / 4 / 8 / 16 / 32 workers. Their application throughput was
approximately 1.02-1.44 MB/s, including request latency, parsing and materialization.
This is not wire throughput or an independently established network ceiling.
All six retained-connection price batches made zero new TCP/TLS handshakes.
Mixed files needed three additional handshakes for their origins.

## Default capacity reasoning

This section describes the earlier stock HTTPX allocator. The redesigned
process-wide allocator and measured defaults are documented in
[HTTP pool engineering](HTTP_POOL.md).

The earlier internal default was 16 connections per transport, shared across origins.
It is a bounded fallback/resource choice, not a request to open 16 connections
and not a limit of 16 concurrent Tickers. HTTP/2 can multiplex many Tickers on
fewer connections, subject to server stream limits and available resources.

The loopback HTTP/1.1 control ran 64 one-byte requests per batch, with 20 ms of
simulated service delay. At 16 / 32 workers, capacity 8 took 0.238 / 0.222 seconds,
capacity 16 took 0.142 / 0.135 seconds, and capacity 32 took 0.152 / 0.093 seconds.
Observed active connections never exceeded the configured cap. These are queue
and fallback capacity measurements, not internet bandwidth measurements.

The live capacity-8 exploration took 1.751 / 2.280 / 4.322 / 7.197 / 18.304 /
42.717 seconds for the same cold batches. These differences alone cannot show
that capacity 16 caused the speed differences; network state also changed.
The final-source capacity-32 exploration took 1.088 / 2.245 / 6.221 / 18.625 /
23.263 / 44.279 seconds, again with matching result fingerprints. All cold price
batches reused connections and made zero additional TCP/TLS handshakes. Increasing
the cap did not establish a consistent gain. Capacity 16 is a conservative
internal default supported by fallback queue control, not a proven universal
optimum. There is no recommended fixed Ticker count for saturating every network;
the same default handles all measured 1/2/4/8/16/32-worker workloads.

## Acceptance and edge cases

The regression suite covers:

| Edge case | Expected behavior / validation |
| --- | --- |
| Different owners and files | Reuse verified TLS H2 connection; local owner close leaves other handles usable. |
| Idle or concurrent GOAWAY | No background traffic; next ranges retry/reconnect and return complete bytes. |
| Active pool eviction / failed pool creation | Active resources remain open; a creation failure preserves the previous idle resource. |
| Same file, eight concurrent filesystems | One footer download and one parsed-index build; sequential reuse preserves footer mtime. |
| Spawned processes and restart | One download in a shared directory, validated disk reuse, unchanged footer mtime. |
| Different cache directories | Shared bytes/index in one process, atomic local copies. |
| Failure and later retry | All waiters receive failure; no poisoned pending entry. |
| Version/hash change or corruption | Reject stale metadata; do not publish invalid or partial cache data. |
| Uncached or cache-failure reads | Real DuckDB query remains on project transport; disabled cache makes no disk writes. |
| Index eviction | Local weak references do not pin globally evicted indexes. |
| Different files and proxy routes | Independent preparation; separate routing identities with bounded resource counts. |

The exact CI unittest command passed locally: 260 tests run, one optional live
HTTP/2 smoke test skipped. The final targeted pytest run passed 196 tests and
27 subtests, with two live tests deselected. GitHub Actions
is configured for Ubuntu, macOS and Windows; remote CI has not yet run.

Four live integration tests passed: DuckDB price/transcripts, representative
Ticker prices, concurrent info and concurrent market-capitalization APIs. The
additional direct Hugging Face HTTP/2 smoke test failed with a HEAD connection
timeout while explicitly bypassing proxies. The existing proxy route succeeded;
the current network therefore did not validate end-to-end direct HF access.
Controlled verified-TLS HTTP/2 tests passed without a proxy. No network or proxy
configuration was changed to obtain these results.

Raw company-network measurements remain under ignored `benchmark/results/local/`.
Files containing `baseline_valid_1`, `baseline_valid_2`, `candidate_16_1`,
`candidate_16_final_valid`, `candidate_8` and `candidate_32` are valid completed runs. The early
`baseline_1` run selected incorrect sources, and `candidate_16_final` failed under
sandbox network restrictions; both are excluded from reported comparisons.
