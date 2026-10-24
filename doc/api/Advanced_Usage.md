<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Advanced Usage](#advanced-usage)
  - [Use SQL to Access Data](#use-sql-to-access-data)
  - [Set Http Proxy (if you’re in a region where cannot access Hugging Face)](#set-http-proxy-if-youre-in-a-region-where-cannot-access-hugging-face)
  - [Set Logging](#set-logging)
  - [Set Configuration](#set-configuration)
  - [Load from Hugging Face](#load-from-hugging-face)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Advanced Usage

## Use SQL to Access Data

SQL syntax reference: [DuckDB.org](https://duckdb.org/)

```python
import defeatbeta_api
import logging
from defeatbeta_api.client.duckdb_client import DuckDBClient
from defeatbeta_api.client.duckdb_client import Configuration
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient
from defeatbeta_api.utils.const import stock_profile

duckdb_client = DuckDBClient(log_level=logging.DEBUG, config=Configuration(duckdb_threads=8))
huggingface_client = HuggingFaceClient()
url = huggingface_client.get_url_path(stock_profile)
sql = f"SELECT * FROM '{url}' WHERE symbol = 'TSLA'"
result = duckdb_client.query(sql)
print(result)
```

## Set Http Proxy (if you’re in a region where cannot access Hugging Face)

```python
import defeatbeta_api
from defeatbeta_api.data.ticker import Ticker

ticker = Ticker("BABA", http_proxy="http://127.0.0.1:8118")
```

`http_proxy=None` (the default) follows the environment proxy settings such as
`HTTPS_PROXY` and `NO_PROXY`. `http_proxy=""` forces direct connections for all
requests, including dataset metadata, and ignores environment proxies.

## Set Logging

```python
import defeatbeta_api
import logging
from defeatbeta_api.data.ticker import Ticker

ticker = Ticker("BABA", log_level=logging.DEBUG)
```

DefeatBeta writes its own diagnostics to standard output without changing the
application's root Python logger. Pytest captures output from passing tests by
default; use `pytest -s` or `pytest --capture=tee-sys` to see these messages
while running a test in a terminal or IDE.

## Set Configuration

```python
import defeatbeta_api
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.data.ticker import Ticker

ticker = Ticker("BABA", config=Configuration())
```

Supported DefeatBeta dataset queries use a process-wide HTTPX transport, including
queries with the local cache disabled and reads that recover from a local cache
failure. DuckDB's native HTTP settings apply to other sources using its native
reader. Most users only need `cache_directory`;
connection sharing requires no additional configuration.

| name | description | default |
|:--|:--|:--|
| duckdb_http_keep_alive | Enable keep-alive in DuckDB's standard HTTP reader; does not control the cache HTTP pool. | True |
| duckdb_http_timeout_seconds | DuckDB HTTP timeout, in seconds. | 120 |
| duckdb_http_retries | DuckDB HTTP retry count. | 5 |
| duckdb_http_retry_backoff | DuckDB HTTP exponential retry factor. | 2.0 |
| duckdb_http_retry_wait_ms | DuckDB HTTP retry wait, in milliseconds. | 1000 |
| duckdb_memory_limit | DuckDB memory limit, as a size such as `10GB` or a percentage of system memory. | '80%' |
| duckdb_threads | Number of DuckDB execution threads; does not set cache download concurrency. | 4 |
| duckdb_parquet_metadata_cache | Enable DuckDB's in-process Parquet metadata cache. | True |
| cache_enabled | Enable demand-driven local caching for supported pinned dataset files. | True |
| cache_directory | Cache root; defaults to a versioned directory under the OS temporary directory. | None |
| cache_data_disk_limit_bytes | Deprecated and ignored; setting it emits a `DeprecationWarning`. Requested data is retained until its dataset version is retired. | None |
| cache_data_memory_limit_bytes | Maximum data-extent bytes in memory; zero disables this tier. At most 64 extents are retained. | 67108864 |
| cache_fetch_workers | Concurrent extent-fetch tasks per filesystem. All filesystems share the process-wide HTTP connection pools. | 16 |
| cache_range_split_bytes | Maximum subrange size when splitting a missing extent into parallel requests; zero disables splitting. | 0 |
| cache_http_timeout_seconds | HTTPX timeout, in seconds, for individual dataset transport operations, including uncached reads; not a whole-download deadline. | 120 |
| cache_prepare_footer_on_first_use | Prepare and persist a Parquet footer when its file is first queried, not at client startup. | True |
| cache_symbol_column_chunk_prefetch | Prefetch matching column chunks for a recognized simple symbol query; useful to disable for diagnostics. | True |
| cache_version_check_interval_seconds | Minimum interval between shared remote dataset-version checks; zero checks before each supported dataset query. | 300 |
| resolve_cdn_for_uncached_reads | Deprecated and ignored. Supported dataset reads always resolve through the shared transport, including when caching is disabled. | True |
| cdn_url_cache_ttl_seconds | In-process TTL for resolved CDN URLs, in seconds. | 1800 |

Metadata requests, CDN resolution and dataset ranges share network transports
across Tickers, files, logging levels and configurations within one process.
Routing and TLS trust settings select separate transports; the shared allocator
separates physical connections by origin. Explicit proxy settings and environment proxy
rules still apply. Resolving a CDN URL does not bypass the selected proxy.

All transports share one process-wide physical connection budget, including
direct requests, proxy requests, and different TLS trust configurations.
HTTP/2 multiplexes requests, so this budget is not a Ticker concurrency limit.
`cache_fetch_workers` limits extent-fetch tasks per filesystem. Closing
one client releases its handles without closing other clients' shared pools.

HTTP connection policy is process-wide, so configure it once before starting
concurrent queries rather than setting conflicting policies on individual Tickers:

```python
from defeatbeta_api.client.http_pool import configure_connection_pool, get_connection_pool_status

configure_connection_pool(
    core_connections_per_origin=4,
    max_connections_for_all_origins=16,
    max_streams_per_connection=4,
    max_connecting_per_origin=4,
    extra_connection_idle_timeout=60,
)
```

| Pool setting | Meaning | Default |
|:--|:--|:--|
| core_connections_per_origin | Best-effort retained connections per origin and proxy/TLS route, established when business requests exhaust existing slots. | 4 |
| max_connections_for_all_origins | Hard physical connection budget for the entire process, across all routes and origins. Connecting and closing connections count against it. | 16 |
| max_streams_per_connection | Client scheduling ceiling, independent of the peer's protocol limit. The effective HTTP/2 limit also obeys peer SETTINGS and the protocol library's limit; `None` adds no extra ceiling. Business requests use HTTP/2 only. | 4 |
| extra_connection_idle_timeout | Continuous idle seconds before surplus connections are reclaimed locally. It sends no network traffic. | 60 |
| max_connecting_per_origin | Maximum concurrent connection initializations per origin and proxy/TLS route after protocol capacity is known. The first connection initializes alone. Demand and the global budget can reduce this bound. | 4 |

Most applications can omit this call and use the defaults. Reconfiguration
rejects active or queued requests and closes idle connections. The process
budget takes precedence over the best-effort core size when many origins are used.

The synchronous API dispatches network operations to one process I/O thread
running httpcore's existing async HTTP/TLS stack. This keeps protocol and TLS
state on one event loop while requests overlap during network waits. It does
not implement a new protocol stack or send background keepalive traffic.
Diagnostic trace callbacks run on this I/O thread and should return promptly.
See [HTTP connection pool](HTTP_Connection_Pool.md) for the complete mechanism,
the meaning of the defaults, and links to engineering measurements.

New requests atomically reserve a slot on a connection with capacity. Core
connections balance slot occupancy; surplus connections receive traffic when
core slots are unavailable. After the first connection establishes protocol
capacity, queued demand can initialize up to `max_connecting_per_origin`
connections concurrently. Expected capacity of connecting sockets avoids
overbuilding for a small burst; it is never used to admit additional streams
before that socket is ready. Requests queue when no eligible slot or expansion
capacity is available, and pool waiting counts against the request's pool timeout.
Available slots are reused before opening another connection, even when the
retained connection count is below the core setting. Core is an idle-retention
target, not an instruction to preconnect or to make requests wait for warmup.

An uncontended request reuses a ready slot immediately under the allocator
lock. One allocator worker handles queued requests and expansion. Each waiting request receives its
own assignment notification, so waiters do not repeatedly scan the whole queue.
Slow idle socket closure runs separately and continues to count against the
global budget until its close attempt finishes. The status counters include
allocator `dispatches` and `close_errors` for diagnosing local management work.

For diagnostics, `get_connection_pool_status()` returns active connections,
their negotiated and effective stream limits, reserved slots, pending requests,
and cumulative allocation metrics. Reservations include assigned requests and
last until the response is closed; they are deliberately more conservative
than counting only open wire streams. A snapshot does not imply that a
connection with available slots has unused network bandwidth.

Ticker initialization no longer sends a one-byte connection prewarm request.
Real business requests reuse eligible connections. There are no periodic HTTP
requests or HTTP/2 PINGs. TCP keepalive is enabled through socket options and
uses OS defaults; it cannot prevent a server from retiring an HTTP session.
httpcore handles protocol-level GOAWAY; the shared allocator stops assigning
unavailable connections and replaces them on demand, with bounded request
retries. An idle connection or expired signed URL is recovered on the next
business request. A fresh process creates its own connection pools.

For caching-enabled reads, validated Parquet footers and immutable parsed
indexes are shared across Tickers and cache directories. Concurrent preparation
of the same file/version has one owner; unrelated files can prepare in parallel.
Footer and index memory caches are each bounded to 32 MiB and 256 entries.
Evicted indexes may be rebuilt from a retained footer without downloading it.
Disk footers survive process restart and use per-file locks for concurrent
processes sharing a directory. Reads preserve footer and data-extent modification
times. Data extents are retained by dataset version, without disk LRU eviction.
Process-local interval indexes are reconstructed at startup and updated by
in-process publication; live index updates from other processes are not supported.
Version changes, changed footer hashes or detected corruption require new
validation. Sharing applies while entries remain valid and retained, rather than
guaranteeing that every file is downloaded exactly once forever.


## Load from Hugging Face

This feature requires additional packages that are not installed by default. Install them first:

```bash
pip install datasets huggingface_hub pyarrow
```

> **Note:** If you have a SOCKS proxy configured in your environment (e.g. `ALL_PROXY=socks5://...`), you may encounter the following error:
> ```
> ImportError: Using SOCKS proxy, but the 'socksio' package is not installed.
> ```
> Fix it by installing `httpx` with SOCKS support:
> ```bash
> pip install "httpx[socks]"
> ```

Load a dataset and inspect available splits:

```python
from datasets import load_dataset
import datasets

datasets.utils.logging.set_verbosity_debug()

dataset = load_dataset(
    "defeatbeta/yahoo-finance-data",
    data_files="data/stock_prices.parquet"
)

# Inspect available splits
print(dataset)

# Access the 'train' split (or whichever split is available)
ds = dataset["train"]

# Split train and test 80% / 20%
split_datasets = ds.train_test_split(test_size=0.2, seed=0xDEADBEAF)
print(split_datasets)
```
