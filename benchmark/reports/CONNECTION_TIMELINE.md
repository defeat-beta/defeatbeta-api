# Connection and request timeline diagnostic

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

Run this diagnostic in a fresh process from the repository root. It uses a
temporary dataset cache and the normal API configuration, including the current
proxy environment. It does not change production connection limits, keepalive
policy, HTTP negotiation, range planning, or retry behavior.

```sh
.venv/bin/python -m benchmark.diagnostics.connection_timeline --output benchmark/results/local/connection_timeline.json
```

The sequence queries different symbols through `price`, `info`, and `calendar`.
It then waits 30, 90, and 150 seconds, querying previously untouched price ranges
after each wait. A final price repeat checks the local cache path. A cache hit
with no network requests cannot establish connection liveness.

For a short capture and an unpatched control with the same initial sequence:

```sh
.venv/bin/python -m benchmark.diagnostics.connection_timeline --skip-idle --output benchmark/results/local/connection_short.json
.venv/bin/python -m benchmark.diagnostics.connection_timeline --baseline --skip-idle --output benchmark/results/local/connection_control.json
```

Compare result fingerprints and downloaded bytes between the records. Network
timings are uncontrolled and a difference between these two runs does not
measure tracing overhead. `event_append_seconds` measures only event appends,
not the total overhead of the diagnostic hooks.

## Reading the record

- All timestamps use one monotonic clock origin and are expressed in nanoseconds.
- `steps` records API calls, result fingerprints, cache counters, and footer mtimes.
- `requests` records HTTPX operations and Requests session operations. Redirected
  Requests operations can be nested, linked by `parent_request_id`.
- `events` contains production timing events, HTTPcore trace events, local DNS,
  TCP connects, TLS handshakes, pool waits, socket reads and writes, worker queues,
  cache validation, disk operations, and cache publication lock spans.
- `transport.pool_wait` measures assignment to a connection.
  `transport.h2_stream_wait` separately measures the HTTP/2 request-slot semaphore;
  it excludes initial semaphore setup and SETTINGS capacity adjustment. The
  installed private source layout is checked before enabling this hook.
- `transport.connect_lock_wait` measures serialization around TCP/TLS or proxy
  tunnel initialization. HTTP/2 initialization, read and write lock waits are
  recorded separately. A read-lock wait can overlap another stream's socket I/O;
  it is not additional exclusive network time.
- `transport.h2_stream_limit` records the peer-advertised and effective local
  stream limits. These limits differ from the physical connection-pool limit.
- The shared query benchmark adds `queries` and `query_id` correlation. Prefetch
  workers retain the triggering query's context. Requests from native execution
  threads may lack attribution; phase reports count such requests explicitly.
- `connection_id` identifies a protocol connection object for the lifetime of
  this diagnostic. Combine it with the local socket port and increasing HTTP/2
  stream IDs to establish reuse across API calls.
- `transport.connection_close.local_idle_expired` says whether the local idle
  deadline had passed when a connection was closed. It does not establish why a
  remote peer closed a connection.
- Requests session timings and HTTPcore spans can be nested. Do not sum them as
  exclusive time or add concurrent request durations to obtain wall-clock time.
- Body timestamps describe bytes delivered to application iterators. They are
  not packet arrival times, physical RTT, or isolated server processing times.
- An HTTP/2 socket read can receive frames for several streams. Its request ID
  identifies the executing request, not ownership of every received byte.
- The socket peer may be a local proxy. Upstream DNS resolution and TCP setup
  performed by that proxy are outside these observations.

Hooks are scoped to the diagnostic context and restored on exit. The script
depends on private synchronous HTTPcore interfaces; it records installed
versions and was verified with HTTPX 0.28.1 and HTTPcore 1.0.9. Records omit URL
queries, headers, bodies, credentials, and exception messages.

The local regression tests cover payload preservation, header/body timing,
cross-file reuse, server-closed connections, existing trace callbacks, hook
restoration after failure, worker isolation, and signature redaction. Live idle
observations apply only to the measured route and time window.

A verified TLS fixture advertising one concurrent stream verifies that three
requests on one connection accumulate stream waiting while connection-pool
waiting stays small. Separate tests verify query-context propagation and merge
overlapping HTTP intervals instead of adding them. Time outside observed HTTP
includes cache/prefetch waiting and Python/DuckDB work; it is not a pure CPU span.
