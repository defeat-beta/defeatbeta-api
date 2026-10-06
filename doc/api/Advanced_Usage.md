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

DuckDB's native reader and the project cache use different HTTP transports. The
`duckdb_` settings below affect only DuckDB; the `cache_` settings affect only
the project's on-demand file cache. Most users only need `cache_directory` and
`cache_data_disk_limit_bytes`.

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
| cache_data_disk_limit_bytes | Maximum retained data-extent bytes on disk. Footer extents are retained separately. This does not trigger full-file downloads. | 5368709120 |
| cache_data_memory_limit_bytes | Maximum data-extent bytes in memory; zero disables this tier. At most 64 extents are retained. | 67108864 |
| cache_fetch_workers | Concurrent cache extent-fetch tasks. One HTTP client per origin can issue concurrent requests and reuse available connections. | 3 |
| cache_range_split_bytes | Maximum subrange size when splitting a missing extent into parallel requests; zero disables splitting. | 0 |
| cache_http_timeout_seconds | HTTPX timeout, in seconds, for individual cache transport operations, not a whole-download deadline. | 120 |
| cache_prepare_footer_on_first_use | Prepare and persist a Parquet footer when its file is first queried, not at client startup. | True |
| cache_symbol_column_chunk_prefetch | Prefetch matching column chunks for a recognized simple symbol query; useful to disable for diagnostics. | True |
| cache_version_check_interval_seconds | Minimum interval between remote dataset-version checks; zero checks before each cached query. | 300 |
| resolve_cdn_for_uncached_reads | Resolve pinned URLs to CDN URLs for the uncached DuckDB reader; cache reads resolve separately. | True |
| cdn_url_cache_ttl_seconds | In-process TTL for resolved CDN URLs, in seconds. | 1800 |

The cache uses one HTTP client per origin, not one physical connection per
origin. `cache_fetch_workers` limits extent-fetch tasks; an HTTP/2 connection
can carry multiple concurrent requests, while the pool can open further
connections when needed. Neither an idle connection nor a signed URL is
guaranteed to remain valid forever; closed connections and expired URLs are
refreshed on demand.


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
