# End-to-end benchmark contract

## Fixed work

Discovery declares W = sampled tickers x all public query operations with frozen
parameters. The sample is chosen before timing, with no automatic replacement
of slow, missing, or failing tickers. The method list is discovered from Ticker;
new required arguments must be declared explicitly. Excel export and diagnostic
output are excluded. Wrapper objects expand into real list/body calls.

All concurrency levels execute identical W exactly once. Workers partition work;
they do not multiply it. Unavailable source bodies stay in the ledger as not
applicable and never count as successful work. Empty successful results remain
valid results. Unexpected failures invalidate acceptance.

## Cache and timing boundaries

Individual latency has two states: independent cold query cache, and exact-task
warmup followed by a repeat call. Query clients and project caches are reset
between individual tasks. Ticker construction is outside API timing and is
recorded separately. HTTP lifecycle remains the product's responsibility.

Throughput has the same two states at concurrency 1/4/16/64/128. A cold batch
starts with one empty shared query cache; sharing within the batch is intentional.
A cached batch first warms all of W and drains prefetch. Generous equal capacities
prevent budget eviction; actual disk capacity and observed cache misses remain
validity checks. Local disk hits qualify alongside memory hits. Native DuckDB
file caching follows each product's defaults and is recorded.

API latency includes complete materialization, internal retries, and waiting.
Warmup, constructor, and result hashing are outside that interval. Throughput
wall time includes executor startup, dispatch, contention, and completion of
all calls. Deferred prefetch is drained after measurement and before cleanup.
Per-phase setup wall time is not API latency or batch throughput.

## Execution and identity

A discovery job resolves the current workload once. Twelve measurement jobs
cover two latency phases plus ten throughput phases. Each phase compares old
and new sources sequentially on the same GitHub runner, alternating AB/BA across
rounds. The first report may omit a baseline. There is no universal historical
absolute-time baseline, and no comparison of hardware across phase jobs.

Export each product from a full commit into an isolated environment with its
original declared dependencies. Freeze harness sources, dependency locks,
Python, environment, source hashes, workflow run and attempt. Each phase uses
a fresh process and isolated cache per variant/round. Prepared environments
cannot be reused after source, harness, or dependency changes.

Current remote data can change daily and historical revisions can disappear.
Observe file/footer identity at measurement time. Require result equality when
inputs match; changed-data pairs retain evidence but receive no faster/slower
verdict. Hash full row multisets and column names without rounding away numeric
differences, outside timed API intervals.

## Evidence and interpretation

Every task must have exactly one completion row with the declared parameters.
Validate observed API coverage, source/dependency identity, finite positive
measurements, fingerprints, completion counters, and all-hit cache conditions.
Combine exactly one copy of all phases from one workflow attempt. Incomplete
jobs, wrong capacities, missing applicability, and errors cannot become success.

Report every ticker/method and all concurrency levels, preserving unfavorable
results. Per-case paired reduction is 100 * (1 - median(candidate / baseline)).
Six or more pairs permit a seeded 2,000-resample bootstrap interval for that
ratio. These intervals are per case without multiplicity correction and are not
a universal performance guarantee. Smaller samples show exploratory medians.

Fixed synthetic Parquet and a local H2 TLS service remain correctness helpers,
with a price oracle and cold/cached cache integration tests. They are not another
user-facing performance experiment. Engineering diagnostics are separate from
release acceptance. No protocol comparison or bandwidth measurement is required.

## Lifecycle

Every measurement is development evidence in Actions Summary and temporary
artifacts. Release finalization separately verifies a complete declared sample,
all phases, at least six even rounds, sources, locks, harness checksums, candidate
tag, and one successful manual workflow attempt. It packages saved evidence
without rerunning measurements or executing downloaded sources. Standalone first
reports and later paired reports share this contract. Existing release assets
are never replaced. See [report lifecycle](results/README.md).
