# Sampled end-to-end calibration

This package prepares the replacement user-visible benchmark contract. The
existing paired benchmark has not yet migrated to this contract. Calibration
is one candidate and one round, not release acceptance or a version comparison.

The fixed 16-symbol sample is AAPL, MSFT, NVDA, JPM, XOM, JNJ, WMT, O, BRK-B,
TSLA, PDD, BABA, NVO, TM, ARM, and CRWV. The list is selected before timing to
include established issuers, recent listings, financial and nonfinancial firms,
non-US issuers, and currency-conversion paths. Discovery records actual price
history sizes, transcript/news availability, and reporting currency. These
observations describe the sample rather than claiming statistical representation
of the full ticker universe. Missing sample symbols fail discovery; they are
never silently replaced using timing results.

All public Ticker query methods are discovered. `dcf()` is Excel export and
`download_data_performance()` is diagnostic output; both are explicitly excluded.
`dcf_data()` remains included. Transcript and news wrappers expand into actual
list and body retrieval. Default arguments and a reporting-currency exchange
pair are frozen. Body identifiers are discovered before timing. An unavailable
body remains in the task ledger as not applicable and is excluded from successful
query throughput. Unexpected query failures remain errors. An added required
parameter stops discovery until an explicit reproducible argument is declared.

The workload is the full Cartesian product of those symbols and operations.
Each throughput concurrency (1, 4, 16, 64, 128) executes the identical workload
exactly once. There are no concurrency-dependent burst sizes. Both latency and
throughput have cold and cached states:

- Individual cold latency: close query clients, clear project metadata/data and
  native query caches, initialize Ticker outside timing, then measure one complete
  API call. HTTP connection lifecycle remains the product's responsibility.
- Individual cached latency: use an isolated environment, warm that exact task,
  drain prefetch, then measure the repeat call.
- Cold throughput: initialize all Tickers with one empty shared query cache, then
  distribute every task to N workers. Natural sharing inside the batch is allowed.
- Cached throughput: warm every ticker/operation pair and drain prefetch, then
  distribute the same complete work. Zero query-data cache misses are required.

An API interval ends only after deferred query results are materialized. Result
hashing, initialization, and warmup are outside it. Throughput wall time includes
executor startup, dispatch, waiting, and completion of all API calls. Cache
validity checks do not constitute separate protocol or bandwidth benchmarks.

The harness prevents disk-budget eviction using a deliberately large logical
limit and records actual physical space. This does not allocate that space or
guarantee that a runner has it. Memory retention is bounded while disk hits count
as local cache hits. Insufficient physical space or measured cache misses make
the cached scenario invalid; the harness never silently calls that all-hit.
Product defaults are unchanged outside the isolated calibration configuration.

Run **Actions > End-to-end benchmark calibration > Run workflow**. It has a
30-minute measurement budget. Completed latency outcomes are flushed individually;
timeouts preserve coverage and cannot become complete-matrix claims. A complete,
error-free run provides rough planning estimates for two- and six-round paired
comparisons. Baseline cost, installation, and environmental variation can change
those estimates. Calibration output remains development evidence in Actions
Summary and 30-day artifacts; nothing is attached to a GitHub Release.

Local runs verify correctness only. Official planning timings come from GitHub.
The product and harness must be committed before running:

```sh
python -m benchmark.e2e.calibrate \
  --output benchmark/results/local/calibration --budget-seconds 1800
```
