# Confirmed blocking of ready HTTP/2 stream data

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

This document records the pre-fix diagnosis. The subsequent implementation and
its validation are described in [HTTP2_RECEIVE_COORDINATION.md](HTTP2_RECEIVE_COORDINATION.md).

## Result

The pinned async httpcore receive path can delay a stream whose data is already
decoded and queued while another stream reads the same connection. This was
reproduced without diagnostic hooks and observed in two real cached-query
batches. Product code, defaults, and protocol scheduling remain unchanged.

The result establishes an avoidable dependency in the receive path. It does not
establish the speedup of a future fix, explain every earlier performance
difference, or justify increasing connection counts.

The general design requirement is that consumption of ready stream data should
not depend on a later socket read undertaken for another stream. Reproduction
uses a particular ordering to expose this requirement; a product design must
apply it uniformly, without symbol, API, response-size, or fast/slow-request
special cases. Existing HTTP framing, TLS, flow control, and error handling
remain responsibilities of the protocol stack.

## Source mechanism

In httpcore 1.0.9, `_receive_stream_event()` checks its stream queue and, when
empty, awaits `_receive_events()`. That method first acquires the connection
read lock, then rechecks the stream queue inside the lock. The AnyIO asyncio
lock transfers ownership to queued waiters in order.

One possible sequence is:

1. Stream A owns the read lock. B and C wait behind it, in that order.
2. A reads data containing an event for C and appends it to C's queue.
3. A releases the lock. B acquires it, finds its own queue empty, and awaits
   another connection read.
4. C's queue is nonempty, but C is already waiting inside lock acquisition.
   It cannot recheck the queue until B releases the lock.

This is a client receive-coordination dependency. It does not require lost TCP
packets, a server delay in sending C's already-received event, or exhausted
connection-pool reservations. B's read can complete with input for any stream;
it is not restricted to B's response.

## Deterministic reproduction

`benchmark/diagnostics/http2_stream_probe.py` constructs valid HTTP/2 frames using hyper-h2
and invokes unchanged httpcore receive methods. A synthetic network backend
gates two reads. Protocol headers are prepared before the observation. Real
TCP, TLS, and CDN behavior are outside this controlled probe.

A reads events for C and A. B's next read is held. At that point the test
directly observes C's DATA in its queue and C's task still pending. Reversing
only B/C waiter order makes C finish before B's input is released. Queue ordering
is established through lock state and explicit gates, not timing guesses.

Both orderings were run with hooks off and on, and with two input delays. All
eight cases returned the expected payloads. Observed enqueue-to-dequeue time
with a waiting consumer, hooks enabled:

| Waiter order | Injected later-input delay | C ready-to-consumption time | C finishes before later input |
| --- | ---: | ---: | --- |
| B, C | 25 ms | 26.455 ms | No |
| C, B | 25 ms | 0.114 ms | Yes |
| B, C | 100 ms | 102.482 ms | No |
| C, B | 100 ms | 0.266 ms | Yes |

The hooks-off cases reproduce the same blocked/completed states. Thus the
dependency is not introduced by tracing. The small timing excess is scheduler
and diagnostic overhead; these delays are not internet latency predictions.

## Event-level diagnostics

`StreamTimeline` temporarily observes each protocol connection's event queues.
It records append/pop timestamps, stream receive-call intervals, body yield,
and the corresponding synchronous bridge return. Queue operations retain list
semantics; hooks do not await, notify a consumer, bypass a lock, or parse frames.
Original dictionaries, lists, and methods are restored after quiescence.

Three different metrics avoid misclassifying buffered data:

- **Queue residence:** enqueue to dequeue, including time before the consumer
  asks for the next event. This can be ordinary buffering or backpressure.
- **Ready with waiting consumer:** residence intersected with the receive call
  that actually consumes the event. No-demand residence is excluded.
- **Ready blocked by another read:** the preceding interval intersected with
  that consumer's read-lock wait and a different stream's socket-read interval
  on the same protocol connection. Intersections are merged to avoid duplication.

Protocol enqueue is after frame decoding/dispatch, not packet arrival. Socket
read intervals include asynchronous resumption and TLS processing. Positive
overlap proves this dependency was present during the observation, but it is
not an estimate of the entire delay that a different implementation would save.

Records contain IDs, timestamps, event types, and byte counts. They omit payloads,
response headers, signed URLs, proxy credentials, and exception text. Existing
diagnostics only enable this additional observer with `--stream-events`.

## Real-query evidence

Network label: the user's last confirmed in-car environment. Routing and TLS
settings were preserved. One round contains two consecutive batches of 128
mixed queries over 32 symbols/four APIs. Footer/index metadata is ready and
data extents are cleared before each batch. No other validation workload ran
during capture.

Dataset: `2026-10-11T04:59:20Z`. Each batch performs 54 Range requests and downloads
47,480,151 bytes. All 256 queries succeeded, with matching result fingerprints
for the 128 symbol/API pairs across batches, no fallback or preparation errors,
and no connection-close errors. DATA-event byte counts match downloaded and
Range-body bytes. All DATA events have ordered enqueue, dequeue, body-yield,
and synchronous-return timestamps. Recorded source hashes were verified.

| Measurement | First batch | Repeat batch |
| --- | ---: | ---: |
| Query P95 | 5.403 s | 3.438 s |
| Batch wall time | 5.811 s | 4.374 s |
| Accumulated pool acquisition time | 7.671 s | 0.0014 s |
| New physical connections | 3 | 0 |
| DATA events | 3,214 | 3,381 |
| DATA events with any confirmed ready-blocked overlap | 489 | 319 |
| DATA events with at least 1 ms confirmed overlap | 306 | 201 |
| Range requests with at least one such 1-ms event | 34 / 54 | 29 / 54 |
| Accumulated confirmed overlap across DATA events | 6.831 s | 3.505 s |
| Longest confirmed overlap for one DATA event | 381.428 ms | 181.720 ms |

The accumulated values overlap across streams and must not be treated as batch
wall time or promised speedup. Detailed tracing adds overhead. These are two
observational batches, not a stable estimate of frequency across networks.
Earlier datasets and differently instrumented captures are not direct controls.

Concrete repeat-batch example, milliseconds from the batch timeline origin:

| Observation | Time |
| --- | ---: |
| Protocol connection 3, stream 17 DATA enqueued | 1509.758 |
| Stream 15 starts a socket read on that connection | 1509.921 |
| Stream 15's socket read returns | 1691.590 |
| Stream 17 dequeues its already-ready DATA | 1692.218 |

Stream 17's consuming receive call is waiting for the read lock during the
overlap. Its ready-with-consumer delay is 182.460 ms, including 181.720 ms of
confirmed other-stream-read overlap. The first-batch worst event is similarly
held behind two other streams' reads after its data has arrived.

This is stronger evidence than observing a long lock wait alone. In the repeat
batch the pool has essentially no admission delay and creates no connections,
yet already-ready stream data still waits inside the receive path.

## Validation and boundaries

Seven new tests cover uninstrumented reproduction, reversed-order control,
enqueue/dequeue attribution and restoration, excluding no-demand buffer residence,
verified-TLS payload/bridge identity, reset/cancellation behavior, and interval
intersection across connection/stream identities. The full local suite executed
336 tests: one skipped, all others passed. Remote CI was not run.

No scheduling fix is included. A future general fix must preserve single-owner
socket reads, per-stream event order, cancellation, response closure, dynamic
SETTINGS, GOAWAY, timeouts, and bounded buffering. A dedicated connection reader
and a readiness-aware waiting mechanism are possible design families; this
diagnostic does not select or implement either. Their complexity and lifecycle
semantics should be assessed before choosing the smallest complete solution.

Local ignored artifacts:

- `results/local/20261011_http2_ready_stream_probe_final.json`: final eight-case
  controlled probe. The earlier file without `_final` is intermediate evidence.
- `results/local/20261011_in_car_http2_stream_events.json`: two real batches with
  full event-level records and source hashes.

```sh
.venv/bin/python -m benchmark.diagnostics.http2_stream_probe \
  --output benchmark/results/local/NEW_UNIQUE_PROBE.json \
  --hold-seconds 0.025 0.1

.venv/bin/python -m benchmark.workloads.http_pool_mixed \
  --output benchmark/results/local/NEW_UNIQUE_STREAM_CAPTURE.json \
  --network-label 'Describe the current network; stream diagnostics enabled' \
  --budgets 16 --concurrency 128 --cache-modes cached \
  --rounds 1 --batches-per-concurrency 2 --stream-events
```
