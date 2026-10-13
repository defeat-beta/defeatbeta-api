# Demand-driven HTTP/2 receive coordination

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

## Change

An owned HTTP/2 connection now admits one caller to httpcore's receive operation
at a time. Other callers await a state-change notification and then return to
their existing response-queue or outgoing-window predicate. They do not queue
for the underlying read lock. A ready stream can therefore consume its events
even when another caller has started the next socket read.

The regression first failed against the previous product path: valid DATA for
stream 5 was queued, but its consumer could not complete while the next input
for stream 3 was withheld. The unchanged assertion passes after the fix, with
that later input still withheld. Reversing waiter order also passes.

`defeatbeta_api/client/http2_receive.py` contains the per-connection adapter.
`ConnectionManager.observe()` installs it once before the first HTTP/2 request
headers are sent, after protocol initialization. Direct and tunneled connections
use the same protocol adapter. Other httpcore users in the process are not
modified. HTTP/1.1 and connection-pool defaults remain unchanged.

The implementation targets the existing pinned httpcore 1.0.9 private API. It
does not implement HTTP framing, TLS, socket I/O, or a new network protocol stack.
It creates no reader task, prefetch queue, polling loop, periodic HTTP request,
or product configuration switch.

## Ownership and lifecycle

- Checking and claiming reader ownership occur without suspension on the single
  HTTP asyncio event loop. At most one caller enters the upstream receiver.
- Notifications replace the event before waking waiters. A waiter observes the
  next event when it needs to wait again, including after an unrelated close.
- The reader releases ownership and notifies in `finally`, including cancellation.
  Cancelling a follower only cancels that follower's wait.
- Response closure notifies waiters, and a removed response queue is reported as
  closed. Connection closure marks the coordinator closed and notifies before
  delegating socket closure to httpcore.
- Shared receive/dispatch/write exceptions terminate the coordinator, mark the
  connection unavailable, and reach pending consumers without another socket
  read. A stream reset is still handled by the upstream stream consumer and
  does not poison the shared receiver.
- GOAWAY is delegated to httpcore for stream-ID classification and retry
  accounting. Existing bounded pool reassignment remains responsible for
  `ConnectionNotAvailable`.
- Socket read/write timeouts still belong to the request performing the upstream
  operation. This change does not add per-stream deadline semantics or alter
  httpcore's connection-wide handling of a read timeout.
- A notification follows completion of the existing receive operation, including
  its outgoing control-data write. Necessary write-lock or socket-write waits
  are not removed. No claim of zero enqueue-to-consumption delay is made.

Class methods are resolved at call time. A persistent connection must not retain
a temporary diagnostic wrapper from the batch in which it was created. A
separate regression failed before this lifecycle correction and passes after it.

## Correctness validation

The full local suite ran 355 tests: 354 passed and one existing opt-in network
test was skipped. Remote CI was not run. The new suite adds 18 tests, including:

- Ready DATA consumption while later input remains blocked, in both waiter orders.
- Reader cancellation and ownership handoff; independent follower cancellation.
- Response and connection closure while consumers wait.
- Read timeout, write timeout, EOF, and an invalid connection-level frame.
- GOAWAY retry classification and request accounting; stream-local reset.
- SETTINGS limit reduction and outgoing WINDOW_UPDATE notification.
- Ordered buffered events without extra reads or prefetch.
- 64 streams over 50 receive rounds: 3,200 DATA events with exact ordering,
  exactly 50 reads, and at most one concurrent read.
- Per-connection, idempotent installation and diagnostic-scope restoration.

Existing verified-TLS tests cover the synchronous bridge, payload identity,
proxy tunneling, physical connection limits, idle GOAWAY recovery, and cache
queries. CI includes the new adapter and regression suite in its triggers and
test command.

## Performance methodology

The benchmark-only `--receive-mode upstream` bypasses adapter installation while
retaining the same current connection pool, cache filesystem, protocol library,
and defaults. `coordinated` runs the product behavior. This is not a historical
0.0.62 versus current-product comparison.

`benchmark.workloads.http_pool_mixed --no-hooks` disables protocol/cache diagnostic hooks
and performance-capture callbacks. Per-query timers and pool sampling remain.
Request/event timing fields with zero samples are unobserved, not evidence of
zero waiting. Results are verified with fingerprints outside the timed queries;
downloaded bytes are taken from filesystem metrics.

Each network run uses one dataset version, prepares four footer/index objects,
clears data blocks before each measured batch, and preserves existing proxy/TLS
settings. Concurrencies 1, 32 and 128 each run twice. Connection counts and
admission delay can differ in expansion batches even with identical defaults.
Sequential runs cannot eliminate internet/CDN variability.

The last user-reported network was in-car; it was not reconfirmed for these runs.
Results must not be compared directly with earlier home/office measurements.
Files before the `final` series are preliminary and precede the diagnostic-scope
correction; they are not the final implementation's performance evidence.

## Final observations

Four sequential runs used the order upstream, coordinated, coordinated,
upstream. All final source hashes were checked against the working tree.

### Verified TLS on loopback

Each mode has six batches per worker count, with 64 queries and exactly
8,388,608 downloaded bytes per batch. All bytes matched the expected payload.
No measured batch created a new connection or reported a request/close error.
Values below are medians across batches, in seconds. CPU includes both the
client and the same-process peer.

| Cache workers | Upstream wall | Coordinated wall | Upstream CPU | Coordinated CPU |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.328030 | 0.307990 | 0.313374 | 0.292133 |
| 16 | 0.271861 | 0.252464 | 0.363081 | 0.338479 |

These samples do not show a median overhead regression. Individual batches
vary; in particular, a single-worker result does not establish a causal gain
from removing inter-stream waiting. This peer is not a CDN or bandwidth test.

### Current external network

All 1,288 measured queries succeeded. The 128 symbol/API fingerprints matched
across runs. Dataset version was `2026-10-11T04:59:20Z` throughout. Each
concurrency downloaded identical bytes in every run: 1,261,289 for one query,
14,486,843 for 32 queries, and 47,480,151 for 128 queries. There were no cache
fallbacks or connection-close errors.

Each table entry is the median of four batch measurements per mode. P95 is
computed inside each batch first; the table does not pool query samples across
batches. For concurrency one, P95 equals that query's latency.

| Concurrent queries | Upstream P95 | Coordinated P95 | Upstream wall | Coordinated wall |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.791734 | 0.694895 | 0.791948 | 0.695100 |
| 32 | 3.051303 | 2.373657 | 3.201536 | 2.394612 |
| 128 | 3.748626 | 4.154668 | 4.946014 | 5.120246 |

The 128-query samples are worse on these aggregate latency measurements:
P95 is approximately 10.8% higher, batch wall time 3.5% higher, and median
application download throughput 3.3% lower. This must not be presented as an
across-the-board throughput or latency improvement. The observed P95 ranges
overlap substantially: upstream 3.364-5.202 seconds, coordinated 3.616-4.591
seconds. Four batches per mode cannot determine whether the difference is a
repeatable product regression or network/CDN/run variation.

The implementation removes the demonstrated client scheduling dependency and
passes correctness checks. Overall external-network performance acceptance,
especially at 128-query concurrency, remains unresolved. Connection counts and
stream defaults were not retuned in response to these samples.

Final local artifacts (ignored by Git):

- `results/local/20261011_receive_final_local_{a,b,c,d}.json`
- `results/local/20261011_receive_final_network_{a,b,c,d}.json`

Letters `a` and `d` are upstream controls; `b` and `c` are coordinated runs.

## Reproduction

```sh
.venv/bin/python -m unittest test.test_http2_receive -v

.venv/bin/python -m benchmark.workloads.http_pool_mixed \
  --output benchmark/results/local/NEW_UNIQUE_RECEIVE.json \
  --network-label 'Describe the current network' \
  --budgets 16 --concurrency 1 32 128 --cache-modes cached \
  --rounds 1 --batches-per-concurrency 2 --no-hooks \
  --receive-mode coordinated

.venv/bin/python -m benchmark.diagnostics.cache_pipeline \
  --output benchmark/results/local/NEW_UNIQUE_LOCAL_RECEIVE.json \
  --workers 1 16 --tasks 64 --rounds 3 --hooks off \
  --receive-mode coordinated
```

Use unique output paths, run candidates sequentially, reverse candidate order,
and retain source hashes and dataset/result identities with the observations.
