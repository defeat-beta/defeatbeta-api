# Office-network HTTP/2 receive validation

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

## Outcome

This run does not establish an across-the-board performance improvement.
The coordinated receiver has a lower aggregate 128-query P95 in this sample,
but single-query latency is higher and 32-query latency is slightly higher.
The earlier 128-query regression was not reproduced in the aggregate office
results; this does not prove it cannot occur on another run or network.

There is no evidence here for increasing the default connection budget.
All 40 batches without new connections had no sampled pending requests and
less than 2 ms of cumulative pool-acquisition time per batch. Expansion
introduced waiting, but the global 16-connection budget was not exhausted.

Single-query process CPU is a follow-up concern. Its batch median increased
from 0.163 s to 1.637 s. High-CPU single-query batches occurred in both modes,
so these results cannot assign the cause to the receiver. They also do not
justify attributing all latency differences to the external network.
Profile the CPU consumer before changing connection or stream defaults.

The subsequent [single-query CPU diagnosis](HTTP2_OFFICE_CPU_DIAGNOSIS.md)
locates a shared DuckDB pending-query/GIL hotspot in native samples of both
receiver modes. The original CPU medians alone do not establish a receiver
regression; an offline reproduction remains the next proposed validation.

## Scope and method

- Network: office, confirmed by the user on 2026-10-12. Earlier home and
  in-car measurements are excluded from this comparison.
- Run start times: 09:12:49, 09:16:24, 09:20:23 and 09:24:08 Asia/Shanghai.
- Order: upstream, coordinated, coordinated, upstream, in separate processes.
- Both modes use the current code after the four review fixes. Upstream
  bypasses only the receive coordinator. This is not a comparison with the
  complete historical 0.0.62 implementation.
- Each run has two rounds, with concurrency order reversed in round two.
  Each concurrency repeats twice per round: eight batches per mode per
  concurrency, 48 measured batches in total.
- One shared Ticker owner; four APIs (`price`, `info`, `calendar`, `dividends`).
  Concurrency 32 means eight symbols times four APIs; concurrency 128 means
  32 symbols times four APIs. Concurrency one measures one `price` query.
- Footer/index objects are prepared before measurement. Data extents are
  cleared before every measured batch. The DuckDB external file cache is
  disabled; its metadata cache remains at its default.
- A fresh pool is created each round, followed by sequential API warmups.
  Later batches reuse demand-created connections. Constructor and warmup
  latency are outside the query measurements.
- Defaults remain: core 4 per origin, global maximum 16 connections,
  4 streams per connection, 4 simultaneous connection initializations per
  origin, 16 cache download workers, and 60 s surplus idle timeout.
- Diagnostic hooks are disabled. Query timers, process CPU accounting,
  filesystem byte metrics and 5 ms pool sampling remain enabled.
- Existing proxy and TLS settings are preserved. No other benchmark or
  test suite was run concurrently by the agent. Other network traffic was
  not controlled or measured.

## Integrity checks

All 2,576 measured queries succeeded. All 128 distinct symbol/API result
fingerprints match across runs. No batch fell back to the uncached reader
or reported a connection-close error. All four reports completed normally.

Dataset version was `2026-10-11T04:59:20Z` throughout. Downloaded bytes match
for every batch at the same concurrency:

| Query concurrency | Downloaded bytes per batch |
| --- | ---: |
| 1 | 1,261,289 |
| 32 | 14,486,843 |
| 128 | 47,480,151 |

Measured batches downloaded 1,011,652,528 bytes in total, excluding warmups.
All eight recorded product-module hashes and all recorded diagnostic hashes
match across runs and match the working tree at analysis time.
Dependencies: DuckDB 1.5.3, HTTPX 0.28.1, httpcore 1.0.9, h2 4.4.1.

## Latency and application throughput

Each value is the median of eight batch measurements. P95 is calculated
within each batch first; query samples are not pooled across batches.
Single-query P95 is simply that query's elapsed time. Throughput is downloaded
application bytes divided by batch wall time plus prefetch drain, in decimal
MB/s. It is not physical link bandwidth.

| Query concurrency | Upstream P95, s | Coordinated P95, s | P95 change | Upstream wall, s | Coordinated wall, s | Upstream MB/s | Coordinated MB/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1.438760 | 1.785060 | +24.07% | 1.439035 | 1.785246 | 0.877 | 0.708 |
| 32 | 9.781867 | 10.100523 | +3.26% | 10.069789 | 10.353937 | 1.439 | 1.402 |
| 128 | 34.293732 | 30.506570 | -11.04% | 38.260514 | 32.031823 | 1.242 | 1.482 |

Batch P95 ranges overlap:

| Query concurrency | Upstream range, s | Coordinated range, s |
| --- | --- | --- |
| 1 | 1.258-2.486 | 1.311-2.413 |
| 32 | 9.216-15.833 | 8.570-14.652 |
| 128 | 26.958-38.197 | 28.162-37.872 |

The 128-query per-run P95 medians, in execution order, were 28.486 s
(upstream A), 30.507 s (coordinated B), 30.465 s (coordinated C), and
35.841 s (upstream D). This order-sensitive variation limits causal claims
from the combined medians. ABBA ordering does not eliminate network/CDN,
host, or workload scheduling variation.

## Connections and waiting

The measured data origin was `https://us.aws.cdn.hf.co:443`, with a peer
stream limit of 100 and an effective local limit of four. This observation
does not enumerate all files or origins on Hugging Face.

At 128-query concurrency, both modes used four CDN connections with a
sampled peak of 16 stream reservations. Total connections peaked at four
or five, depending on whether the idle Hugging Face metadata connection
was still present. No sample showed waiting at a fully reserved global
connection budget.

Eight expansion batches each created three connections, with eight or nine
sampled pending requests and 5.962-7.823 s of cumulative pool-acquisition
time. This is summed time across requests, not an additional batch delay.
The other 40 batches created no connections, had no sampled pending
requests, and had at most 0.001970 s of cumulative pool-acquisition time.
The 5 ms sampler can miss brief queue peaks.

These observations support retaining the current budget for this cached
mixed-API workload. They do not establish that four CDN connections are
universally optimal or that the office network bandwidth was saturated.
Cache-worker queues, time to first byte and socket waiting were not traced
in these runs; zero-sample timing fields are unobserved, not zero waiting.

## Process CPU observation

| Query concurrency | Upstream median CPU, s | Coordinated median CPU, s |
| --- | ---: | ---: |
| 1 | 0.162758 | 1.637344 |
| 32 | 10.387072 | 7.689304 |
| 128 | 30.630324 | 20.450626 |

CPU is summed over the process threads during a batch and includes pool
sampling and query execution. These are not exclusive networking costs.
Single-query batches split between approximately 0.14-0.18 CPU seconds
and approximately 1.3-2.3 CPU seconds. Both modes have high-CPU batches;
the coordinated mode has more of them in this sample. The current
instrumentation cannot identify the responsible thread or call stack.

## Artifacts and reproduction

Raw local reports are ignored by Git:

- `results/local/20261012_office_review_a.json`: upstream
- `results/local/20261012_office_review_b.json`: coordinated
- `results/local/20261012_office_review_c.json`: coordinated
- `results/local/20261012_office_review_d.json`: upstream

Run the following sequentially with unique output paths and modes in the
order listed above. Do not overlap a run with other validation workloads.

```sh
.venv/bin/python -m benchmark.workloads.http_pool_mixed \
  --output benchmark/results/local/NEW_UNIQUE_OFFICE_RESULT.json \
  --network-label 'Office network; record current date and code state' \
  --budgets 16 --concurrency 1 32 128 --cache-modes cached \
  --rounds 2 --batches-per-concurrency 2 --no-hooks \
  --receive-mode coordinated
```
