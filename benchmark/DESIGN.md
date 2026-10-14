# Paired benchmark design

## Experiment identity

Resolve baseline and candidate Git refs once. Export product sources and install
each into a separate virtual environment, using that version's dependencies and
defaults. Save full commits, product source hashes, dependency locks, Python,
CPU/RAM/platform, runner image, and proxy route. Both versions use one frozen
harness. Changed harness sources, product files, or prepared dependencies prevent
reuse of an experiment.

A/B run sequentially on one host with alternating AB/BA order. Six even paired
rounds balance order for release evidence. Each variant/case/round has a new
interpreter and isolated cache. Controlled H2, controlled H1, and the live service
run as separate jobs; their absolute times cannot be compared directly. A GitHub
runner label does not fix the physical CPU or public network route.

## Data and network paths

Controlled mode generates one deterministic synthetic fixture before A/B with
DuckDB `2.0.0.dev2610011535`. Both products read those same bytes. The fixture
contains 33 symbols including SPY, 13 Parquet files, varied history lengths,
multiple row groups, compressed/uncompressed tables, and nested payloads. Full
file/footer hashes and the generator identity are retained. An independent
price count/min/max oracle is tested; other APIs currently use A/B equality.

A separate Hypercorn 0.17.3 process serves actual HTTPS, redirects, and Range
responses. A verified test CA and ALPN exercise HTTP/2 or HTTP/1.1. Metadata and
data use two origins, 127.0.0.1 and localhost. The adapter redirects endpoints,
while preserving each product's actual cache, pool, HTTP, TLS, and SQL paths.
It does not inject results or replace transport with mocks.

The server records CPU/RSS, protocol, request, and byte counters. Loopback is
unshaped and server capacity has not been calibrated. Host resources are shared
with the server. This mode does not establish an absolute client bandwidth limit.

Live mode keeps the normal product path to current Hugging Face main. Historical
revisions can be deleted, so availability of old commits is not assumed. Record
observed update_time and file/footer metadata. Daily changes are accepted; when
metadata differs inside a pair, keep timing, waive cross-input result equality,
and label the case inconclusive. Controlled samples and live samples with equal
metadata must have matching results. Daily updates do not alter the controlled
baseline.

## Workloads and states

Suite v2 declares 32 cross-sector symbols and seed 1729. This is a predeclared
corpus, not automatic stratification against the current remote files. Each
method uses one selected symbol; mixed traffic spans the corpus. Selection is
frozen before either product runs and never depends on favorable timings.

The 20 methods include nine direct reads, quarterly income/balance/cash-flow and
revenue breakdown, market capitalization, trailing PE, beta, and transcript/news
lists and bodies. Discovery freezes body identifiers before A/B; timed body
calls actually materialize their content. The saved API coverage map explicitly
identifies unmeasured related methods and presentation/export/AI exclusions.

| State | Preparation and primary duration |
| --- | --- |
| First use | Empty application cache in a fresh process; Ticker constructor plus API. |
| Memory warm | Materialize selected call and drain prefetch in the same process; time repeat API. |
| Disk warm | Seed cache in another process; new interpreter measures constructor plus API. |
| Metadata ready (project-only diagnostic) | Warm each distinct method, drain prefetch, clear data extents and memory blocks, retain metadata; time API. |

The first-result metric sums constructor and API intervals; it excludes Python
startup/imports and harness setup between these intervals. Metadata-ready
connections can be reused while still live; preparation does not guarantee they
remain open. Application cache preparation does not flush DNS, OS pages, proxy,
or remote CDN caches. The default policy leaves each product's native
`enable_external_file_cache` setting unchanged. The project-only diagnostic sets
it to false to isolate `DatasetCacheFileSystem`. Neither policy uses the
`cache_httpfs` extension. Initial and effective engine settings are recorded per
measurement; missing or inconsistent observations invalidate suite v2 evidence.
Other product defaults remain intact; the suite does not require pool tuning.

The default release contract has 20 methods times three states plus ten
concurrent cases, totaling 70. Metadata-only preparation is excluded from this
contract because clearing project extents would leave the native cache warm.
The separate project-only diagnostic retains all four states and 90 cases. Its
policy is included in the suite and each case, and changes the suite checksum.
It cannot be promoted as default-behavior release evidence.

A burst synchronizes N calls; a bounded stream executes the same 128-task plan at
concurrency 1, 4, 16, 64, and 128. The plan mixes price/info/shares/filings. Data
starts cold but natural sharing and cache hits develop during each batch. Under
the default policy, each batch starts without query warmup; under project-only,
each batch uses metadata-only preparation with the native file cache disabled.
Calls/s measures mixed-query completion, not sustained uncached download speed.
Smoke mode reduces methods, states, and concurrency levels.

## Metrics and correctness

Measure fully materialized call latency, batch wall time, empirical within-batch
P95, CPU, RSS at query end (not peak), bytes, Range requests, prefetch drain, and
available pool counters. Missing old-version counters are unavailable, not zero.
Thread-pool queue time is separate; batch wall time includes dispatch/completion.
Post-query prefetch is drained before cleanup. Query and post-drain byte totals
remain distinct. Constructor and preparation CPU are separate from query CPU.
Overlapping diagnostic spans must not be summed into exclusive phases.

Result hashing occurs after the timed query interval. Fingerprints include
column names and the complete row multiset, preserve duplicate rows, and do not
round numeric differences away. Missing pairs, duplicate/undeclared samples,
failed workers, missing fingerprints, nonfinite times, manifest changes, or
applicable result mismatches invalidate comparison. Failures are retained rather
than replaced with successful retries. Disk-cache seeding records are retained.

Per-case reduction is `100 * (1 - median(candidate / baseline per pair))`.
At least six pairs permit a 2,000-resample bootstrap interval for the paired
median ratio; smaller samples remain exploratory. These are per-case intervals
without multiple-comparison adjustment. There is no calibrated materiality
threshold or automatic performance-regression gate. Correctness/completeness
failures fail the job. Slower and inconclusive cases stay visible for review.

## Report lifecycle

Every measurement produces development JSON/Markdown, job Summary, and temporary
Artifacts. Even the full release suite does not create a final release report.
Ordinary workflows have no publication permission. Git ignore rules concern
local files and do not control remote publication.

A separate manual workflow selects one complete successful run and an existing
Release tag identifying the candidate commit. It verifies all three experiments,
balanced rounds, source/dependency/harness identity, and one workflow attempt.
It renders saved evidence without executing downloaded code or rerunning queries,
then uploads a detailed Markdown report and checksummed evidence bundle to that
Release. Existing assets are never replaced. It does not create tags or publish
software. See [report lifecycle](results/README.md).

The bundle retains raw evidence, readable reports, commits, dependency locks,
and the frozen harness. Temporary source paths describe the original runner;
reconstruction uses the commits and locks. A complete valid report is evidence
for a release decision, not an assertion that every API or network improved.
